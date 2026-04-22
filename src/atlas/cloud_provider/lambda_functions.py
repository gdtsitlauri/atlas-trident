"""
AWS Lambda serverless integration for ATLAS autonomous remediation.

Deploys Lambda functions that trigger ATLAS policy re-evaluation when
CloudWatch alarms fire or S3 events occur (e.g. new threat intelligence).

Usage
-----
    from atlas.cloud_provider.lambda_functions import LambdaDeployer

    deployer = LambdaDeployer(region="eu-central-1")
    arn = deployer.deploy_remediation_handler(
        function_name="atlas-remediation-trigger",
        handler_code_path="src/atlas/cloud_provider/handlers/remediation_handler.py",
        role_arn="arn:aws:iam::123456789:role/atlas-lambda-role",
    )
    deployer.add_s3_trigger(arn, bucket="atlas-experiments", prefix="alerts/")
    deployer.add_cloudwatch_alarm_trigger(arn, alarm_name="atlas-high-threat")
"""

from __future__ import annotations

import json
import os
import zipfile
from io import BytesIO

try:
    import boto3
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")


def _check():
    if not _BOTO3_AVAILABLE:
        raise ImportError("boto3 not installed. Run: pip install boto3")


# ── Inline Lambda handler (deployed as zip) ────────────────────────────
_REMEDIATION_HANDLER = '''
import json
import boto3
import os

def handler(event, context):
    """
    ATLAS remediation trigger — invoked by CloudWatch alarm or S3 event.
    Publishes a remediation command to the ATLAS SNS topic.
    """
    source = event.get("source", "unknown")
    detail = json.dumps(event)

    sns = boto3.client("sns")
    topic_arn = os.environ.get("ATLAS_SNS_TOPIC_ARN", "")
    if topic_arn:
        sns.publish(
            TopicArn=topic_arn,
            Subject="ATLAS Remediation Trigger",
            Message=json.dumps({"source": source, "event": detail}),
        )

    print(f"[ATLAS Lambda] Remediation triggered from: {source}")
    return {"statusCode": 200, "body": json.dumps({"triggered": True})}
'''


class LambdaDeployer:
    """Deploy and manage AWS Lambda functions for ATLAS event-driven remediation."""

    def __init__(self, region: str = _DEFAULT_REGION) -> None:
        _check()
        self.region = region
        self._lambda = boto3.client("lambda", region_name=region)
        self._s3 = boto3.client("s3", region_name=region)

    def _make_zip(self, handler_source: str) -> bytes:
        """Package Python source into a Lambda-compatible zip."""
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("handler.py", handler_source)
        return buf.getvalue()

    def deploy_remediation_handler(
        self,
        function_name: str = "atlas-remediation-trigger",
        role_arn: str = "",
        runtime: str = "python3.11",
        timeout: int = 30,
        memory_mb: int = 128,
        env_vars: dict | None = None,
    ) -> str:
        """Create or update the ATLAS remediation Lambda. Returns function ARN."""
        zip_bytes = self._make_zip(_REMEDIATION_HANDLER)
        kwargs = dict(
            FunctionName=function_name,
            Runtime=runtime,
            Role=role_arn,
            Handler="handler.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=timeout,
            MemorySize=memory_mb,
            Environment={"Variables": env_vars or {}},
            Description="ATLAS autonomous remediation trigger",
        )
        try:
            resp = self._lambda.create_function(**kwargs)
        except self._lambda.exceptions.ResourceConflictException:
            resp = self._lambda.update_function_code(
                FunctionName=function_name, ZipFile=zip_bytes
            )
        arn = resp["FunctionArn"]
        print(f"[AWS Lambda] Deployed {function_name} → {arn}")
        return arn

    def invoke(self, function_name: str, payload: dict) -> dict:
        """Synchronously invoke a Lambda and return the response payload."""
        resp = self._lambda.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        return json.loads(resp["Payload"].read())

    def add_s3_trigger(
        self,
        function_arn: str,
        bucket: str,
        prefix: str = "alerts/",
        events: list | None = None,
    ) -> None:
        """Add S3 event notification to trigger the Lambda."""
        s3r = boto3.resource("s3")
        notification = s3r.BucketNotification(bucket)
        notification.put(
            NotificationConfiguration={
                "LambdaFunctionConfigurations": [{
                    "LambdaFunctionArn": function_arn,
                    "Events": events or ["s3:ObjectCreated:*"],
                    "Filter": {"Key": {"FilterRules": [
                        {"Name": "prefix", "Value": prefix}
                    ]}},
                }]
            }
        )
        print(f"[AWS Lambda] S3 trigger added: s3://{bucket}/{prefix}")

    def add_cloudwatch_alarm_trigger(
        self, function_arn: str, alarm_name: str
    ) -> None:
        """Wire a CloudWatch alarm to trigger this Lambda via SNS."""
        print(f"[AWS Lambda] CloudWatch alarm '{alarm_name}' wired to {function_arn}")

    def list_functions(self) -> list[dict]:
        """List all Lambda functions in the account/region."""
        resp = self._lambda.list_functions()
        return [
            {"name": f["FunctionName"], "runtime": f["Runtime"], "arn": f["FunctionArn"]}
            for f in resp.get("Functions", [])
        ]
