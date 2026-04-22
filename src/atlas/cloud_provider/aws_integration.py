"""
AWS integration for ATLAS cloud autonomy framework.

Provides S3 artifact storage, EC2 instance management, and
CloudWatch metrics logging for ATLAS digital-twin experiments.

Credentials
-----------
Set via environment variables (never hard-code):
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION   (default: eu-central-1)

Or use an IAM role if running on EC2.

Usage
-----
    from atlas.cloud_provider.aws_integration import AWSProvider

    aws = AWSProvider(bucket="atlas-experiments")
    aws.upload_artifact("results/run_42.json", "atlas/runs/run_42.json")
    aws.log_metric("neutralization_rate", 0.919, namespace="ATLAS/CoEvo")
    instances = aws.list_running_instances()
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import boto3
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False


_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")


def _check():
    if not _BOTO3_AVAILABLE:
        raise ImportError("boto3 not installed. Run: pip install boto3")


class AWSProvider:
    """AWS cloud provider for ATLAS experiment artifact management."""

    def __init__(
        self,
        bucket: str = "atlas-experiments",
        region: str = _DEFAULT_REGION,
    ) -> None:
        _check()
        self.bucket = bucket
        self.region = region
        self._s3 = boto3.client("s3", region_name=region)
        self._ec2 = boto3.client("ec2", region_name=region)
        self._cw = boto3.client("cloudwatch", region_name=region)

    # ── S3 artifact storage ────────────────────────────────────────────

    def upload_artifact(self, local_path: str, s3_key: str) -> str:
        """Upload a local file to S3. Returns the s3:// URI."""
        self._s3.upload_file(local_path, self.bucket, s3_key)
        uri = f"s3://{self.bucket}/{s3_key}"
        print(f"[AWS S3] Uploaded {local_path} → {uri}")
        return uri

    def download_artifact(self, s3_key: str, local_path: str) -> None:
        """Download an S3 object to a local path."""
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._s3.download_file(self.bucket, s3_key, local_path)
        print(f"[AWS S3] Downloaded s3://{self.bucket}/{s3_key} → {local_path}")

    def upload_results(self, results: dict[str, Any], run_id: str) -> str:
        """Serialize and upload a results dict as JSON."""
        tmp = Path(f"/tmp/atlas_run_{run_id}.json")
        tmp.write_text(json.dumps(results, indent=2))
        return self.upload_artifact(str(tmp), f"atlas/runs/{run_id}.json")

    def list_artifacts(self, prefix: str = "atlas/") -> list[str]:
        """List all S3 keys under a prefix."""
        resp = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", [])]

    # ── CloudWatch metrics ─────────────────────────────────────────────

    def log_metric(
        self,
        name: str,
        value: float,
        namespace: str = "ATLAS/CoEvolution",
        unit: str = "None",
    ) -> None:
        """Push a single metric data-point to CloudWatch."""
        self._cw.put_metric_data(
            Namespace=namespace,
            MetricData=[{
                "MetricName": name,
                "Value": value,
                "Unit": unit,
                "Timestamp": datetime.utcnow(),
            }],
        )

    def log_experiment(
        self,
        metrics: dict[str, float],
        namespace: str = "ATLAS/CoEvolution",
    ) -> None:
        """Push multiple metrics to CloudWatch in one call."""
        metric_data = [
            {"MetricName": k, "Value": float(v), "Unit": "None",
             "Timestamp": datetime.utcnow()}
            for k, v in metrics.items()
            if isinstance(v, (int, float))
        ]
        if metric_data:
            self._cw.put_metric_data(Namespace=namespace, MetricData=metric_data)

    # ── EC2 instance management ────────────────────────────────────────

    def list_running_instances(self) -> list[dict]:
        """Return running EC2 instances with id, type, and public IP."""
        resp = self._ec2.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
        instances = []
        for reservation in resp["Reservations"]:
            for inst in reservation["Instances"]:
                instances.append({
                    "id":         inst["InstanceId"],
                    "type":       inst["InstanceType"],
                    "public_ip":  inst.get("PublicIpAddress", "N/A"),
                    "launch_time": str(inst["LaunchTime"]),
                })
        return instances

    def get_instance_status(self, instance_id: str) -> str:
        """Return the state of a specific EC2 instance."""
        resp = self._ec2.describe_instances(InstanceIds=[instance_id])
        state = resp["Reservations"][0]["Instances"][0]["State"]["Name"]
        return state
