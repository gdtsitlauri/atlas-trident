"""
AWS SageMaker integration for ATLAS ML training and endpoint deployment.

Covers the full MLOps lifecycle on SageMaker:
  - Training job submission (custom container or built-in algorithms)
  - Real-time inference endpoint creation and invocation
  - Batch transform for large-scale evaluation
  - Model registry versioning

Usage
-----
    from atlas.cloud_provider.sagemaker_integration import SageMakerProvider

    sm = SageMakerProvider(role_arn="arn:aws:iam::123:role/SageMakerRole")

    # Submit training job
    job = sm.submit_training_job(
        job_name="atlas-coevo-seed42",
        image_uri="763104351884.dkr.ecr.eu-central-1.amazonaws.com/pytorch-training:2.1-gpu-py310",
        s3_input="s3://atlas-experiments/data/cicids2017/",
        s3_output="s3://atlas-experiments/models/",
        instance_type="ml.g4dn.xlarge",
    )

    # Deploy endpoint
    endpoint = sm.deploy_endpoint("atlas-coevo-seed42", instance_type="ml.t2.medium")
    result = sm.invoke_endpoint(endpoint, payload={"features": [...]})
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

try:
    import boto3
    import sagemaker
    from sagemaker.estimator import Estimator
    from sagemaker.predictor import Predictor
    _SM_AVAILABLE = True
except ImportError:
    _SM_AVAILABLE = False

_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")


def _check():
    if not _SM_AVAILABLE:
        raise ImportError(
            "sagemaker SDK not installed. Run: pip install sagemaker boto3"
        )


class SageMakerProvider:
    """AWS SageMaker provider for ATLAS ML training and inference."""

    def __init__(
        self,
        role_arn: str = "",
        region: str = _DEFAULT_REGION,
        bucket: str = "atlas-experiments",
    ) -> None:
        _check()
        self.role_arn = role_arn or os.getenv("SAGEMAKER_ROLE_ARN", "")
        self.region = region
        self.bucket = bucket
        self._sm_client = boto3.client("sagemaker", region_name=region)
        self._runtime = boto3.client("sagemaker-runtime", region_name=region)

    # ── Training jobs ──────────────────────────────────────────────────

    def submit_training_job(
        self,
        job_name: str,
        image_uri: str,
        s3_input: str,
        s3_output: str,
        instance_type: str = "ml.g4dn.xlarge",
        instance_count: int = 1,
        hyperparameters: dict | None = None,
        volume_gb: int = 30,
    ) -> str:
        """Submit a SageMaker training job. Returns job name."""
        self._sm_client.create_training_job(
            TrainingJobName=job_name,
            AlgorithmSpecification={
                "TrainingImage": image_uri,
                "TrainingInputMode": "File",
            },
            RoleArn=self.role_arn,
            InputDataConfig=[{
                "ChannelName": "training",
                "DataSource": {"S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": s3_input,
                    "S3DataDistributionType": "FullyReplicated",
                }},
            }],
            OutputDataConfig={"S3OutputPath": s3_output},
            ResourceConfig={
                "InstanceType": instance_type,
                "InstanceCount": instance_count,
                "VolumeSizeInGB": volume_gb,
            },
            StoppingCondition={"MaxRuntimeInSeconds": 86400},
            HyperParameters={str(k): str(v) for k, v in (hyperparameters or {}).items()},
        )
        print(f"[SageMaker] Training job submitted: {job_name}")
        return job_name

    def wait_for_training(self, job_name: str, poll_interval: int = 60) -> str:
        """Poll until training job completes. Returns final status."""
        while True:
            resp = self._sm_client.describe_training_job(TrainingJobName=job_name)
            status = resp["TrainingJobStatus"]
            print(f"[SageMaker] {job_name}: {status}")
            if status in ("Completed", "Failed", "Stopped"):
                return status
            time.sleep(poll_interval)

    def get_training_metrics(self, job_name: str) -> list[dict]:
        """Return final metric values logged during training."""
        resp = self._sm_client.describe_training_job(TrainingJobName=job_name)
        return resp.get("FinalMetricDataList", [])

    # ── Model deployment ───────────────────────────────────────────────

    def deploy_endpoint(
        self,
        model_name: str,
        endpoint_name: str | None = None,
        instance_type: str = "ml.t2.medium",
        initial_instance_count: int = 1,
    ) -> str:
        """Create a real-time inference endpoint. Returns endpoint name."""
        endpoint_name = endpoint_name or f"{model_name}-endpoint"
        config_name = f"{endpoint_name}-config"

        self._sm_client.create_endpoint_config(
            EndpointConfigName=config_name,
            ProductionVariants=[{
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "InitialInstanceCount": initial_instance_count,
                "InstanceType": instance_type,
                "InitialVariantWeight": 1.0,
            }],
        )
        self._sm_client.create_endpoint(
            EndpointName=endpoint_name,
            EndpointConfigName=config_name,
        )
        print(f"[SageMaker] Endpoint deploying: {endpoint_name}")
        return endpoint_name

    def invoke_endpoint(
        self,
        endpoint_name: str,
        payload: Any,
        content_type: str = "application/json",
    ) -> Any:
        """Invoke a SageMaker endpoint for real-time inference."""
        body = json.dumps(payload) if not isinstance(payload, str) else payload
        resp = self._runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType=content_type,
            Body=body.encode(),
        )
        return json.loads(resp["Body"].read())

    def delete_endpoint(self, endpoint_name: str) -> None:
        """Delete an endpoint to stop incurring charges."""
        self._sm_client.delete_endpoint(EndpointName=endpoint_name)
        print(f"[SageMaker] Endpoint deleted: {endpoint_name}")

    def list_endpoints(self) -> list[dict]:
        """List all SageMaker endpoints and their statuses."""
        resp = self._sm_client.list_endpoints()
        return [
            {"name": e["EndpointName"], "status": e["EndpointStatus"]}
            for e in resp.get("Endpoints", [])
        ]
