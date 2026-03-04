from __future__ import annotations

import base64
import json

import httpx
import structlog

from shared.errors import ApifyError

logger = structlog.get_logger()

APIFY_API_BASE = "https://api.apify.com/v2"


def base64_encode_webhooks(webhooks: list[dict]) -> str:
    """Encode webhooks as base64 for Apify query parameter."""
    return base64.b64encode(json.dumps(webhooks).encode()).decode()


class ApifyClient:
    def __init__(self, api_token: str, actor_id: str, webhook_base_url: str) -> None:
        self._api_token = api_token
        self._actor_id = actor_id
        self._webhook_base_url = webhook_base_url

    def start_actor_run(self, source_url: str, task_id: str) -> str:
        """Start an Apify actor run for the given URL.

        Returns the Apify run ID.
        """
        webhook_url = f"{self._webhook_base_url}/api/v1/webhooks/apify?task_id={task_id}"

        run_url = f"{APIFY_API_BASE}/acts/{self._actor_id}/runs"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }
        params = {
            "webhooks": base64_encode_webhooks([
                {
                    "eventTypes": ["ACTOR.RUN.SUCCEEDED"],
                    "requestUrl": webhook_url,
                }
            ]),
        }

        # Actor input — startUrls + proxy are required by this TikTok actor
        actor_input = {
            "startUrls": [source_url],
            "proxy": {
                "useApifyProxy": True,
            },
        }

        log = logger.bind(task_id=task_id, source_url=source_url)
        log.info("starting_apify_actor_run", webhook_url=webhook_url)

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    run_url, json=actor_input, headers=headers, params=params
                )
                response.raise_for_status()
                data = response.json()
                run_id = data["data"]["id"]
                log.info("apify_run_started", run_id=run_id)
                return run_id
        except httpx.HTTPStatusError as e:
            raise ApifyError(f"Apify API error {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise ApifyError(f"Failed to start Apify run: {e}") from e
