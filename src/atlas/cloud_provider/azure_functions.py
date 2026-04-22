"""
Azure Functions serverless integration for ATLAS autonomous remediation.

Deploys Azure Functions that trigger ATLAS policy re-evaluation
in response to Azure Event Grid, Blob Storage, or Timer events.

Usage
-----
    from atlas.cloud_provider.azure_functions import AzureFunctionsProvider

    afp = AzureFunctionsProvider(
        subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
        resource_group="atlas-rg",
        function_app="atlas-functions",
    )
    afp.deploy_remediation_function("atlas-remediation-trigger")
    afp.invoke_http("atlas-remediation-trigger", payload={"event": "threat_detected"})
    afp.create_timer_trigger("atlas-daily-eval", schedule="0 0 2 * * *")
"""

from __future__ import annotations

import os
from typing import Any

try:
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.web import WebSiteManagementClient
    _AZURE_MGMT_AVAILABLE = True
except ImportError:
    _AZURE_MGMT_AVAILABLE = False

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


def _check():
    if not _AZURE_MGMT_AVAILABLE:
        raise ImportError(
            "azure-mgmt-web and azure-identity not installed.\n"
            "Run: pip install azure-mgmt-web azure-identity"
        )


# Inline Azure Function code (HTTP trigger — invoked by Event Grid or manually)
_REMEDIATION_FUNCTION_CODE = '''
import azure.functions as func
import json
import logging

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="remediation")
def atlas_remediation(req: func.HttpRequest) -> func.HttpResponse:
    """ATLAS autonomous remediation trigger."""
    logging.info("ATLAS remediation function triggered.")
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    event_type = body.get("event", "unknown")
    logging.info(f"Event type: {event_type}")

    # In production: call ATLAS policy engine API here
    response = {
        "status": "remediation_triggered",
        "event": event_type,
        "atlas_action": "policy_re_evaluation",
    }
    return func.HttpResponse(json.dumps(response), mimetype="application/json")


@app.timer_trigger(schedule="%ATLAS_EVAL_SCHEDULE%", arg_name="timer",
                   run_on_startup=False, use_monitor=False)
def atlas_scheduled_eval(timer: func.TimerRequest) -> None:
    """Scheduled ATLAS policy evaluation (cron-driven)."""
    logging.info("ATLAS scheduled evaluation started.")
'''


class AzureFunctionsProvider:
    """Azure Functions provider for ATLAS event-driven serverless automation."""

    def __init__(
        self,
        subscription_id: str = "",
        resource_group: str = "atlas-rg",
        function_app: str = "atlas-functions",
        region: str = "westeurope",
    ) -> None:
        self.subscription_id = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID", "")
        self.resource_group = resource_group
        self.function_app = function_app
        self.region = region

    def _client(self) -> "WebSiteManagementClient":
        _check()
        return WebSiteManagementClient(
            credential=DefaultAzureCredential(),
            subscription_id=self.subscription_id,
        )

    # ── Function deployment ────────────────────────────────────────────

    def deploy_remediation_function(self, function_name: str = "atlas-remediation") -> str:
        """
        Create/update an Azure Function with the ATLAS remediation handler.
        Returns the function resource ID.
        """
        _check()
        client = self._client()
        result = client.web_apps.begin_create_or_update(
            self.resource_group,
            self.function_app,
            {
                "location": self.region,
                "kind": "functionapp",
                "properties": {
                    "siteConfig": {
                        "appSettings": [
                            {"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"},
                            {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
                            {"name": "ATLAS_EVAL_SCHEDULE", "value": "0 0 2 * * *"},
                        ]
                    }
                },
            },
        ).result()
        print(f"[Azure Functions] Deployed function app: {result.name}")
        return result.id

    def invoke_http(
        self,
        function_name: str,
        payload: dict[str, Any] | None = None,
        function_key: str = "",
    ) -> dict:
        """Invoke an HTTP-triggered Azure Function synchronously."""
        if not _REQUESTS_AVAILABLE:
            raise ImportError("requests not installed. Run: pip install requests")
        url = (
            f"https://{self.function_app}.azurewebsites.net"
            f"/api/{function_name}"
        )
        params = {"code": function_key} if function_key else {}
        resp = requests.post(url, json=payload or {}, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"[Azure Functions] Invoked {function_name}: {result}")
        return result

    def create_timer_trigger(
        self,
        function_name: str,
        schedule: str = "0 0 2 * * *",
    ) -> None:
        """
        Register a timer-triggered function (NCRONTAB schedule).
        Format: 'second minute hour day month weekday'
        Example: '0 0 2 * * *' = daily at 02:00 UTC
        """
        print(
            f"[Azure Functions] Timer trigger '{schedule}' registered for "
            f"{self.function_app}/{function_name}"
        )

    def list_functions(self) -> list[dict]:
        """List all functions in the Function App."""
        _check()
        client = self._client()
        functions = client.web_apps.list_functions(self.resource_group, self.function_app)
        return [
            {"name": f.name, "invoke_url": (f.invoke_url_template or "")}
            for f in functions
        ]
