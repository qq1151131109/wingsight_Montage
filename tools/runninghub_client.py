"""Shared RunningHub OpenAPI helpers for image and video tools."""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


RUNNINGHUB_BASE_URL = "https://www.runninghub.cn/openapi/v2"
RUNNINGHUB_TERMINAL_STATUSES = {"SUCCESS", "FAILED"}
RUNNINGHUB_ACTIVE_STATUSES = {"QUEUED", "RUNNING"}


def get_runninghub_api_key() -> str | None:
    """Return the configured RunningHub API key, if present."""
    return os.environ.get("RUNNINGHUB_API_KEY")


def normalize_runninghub_status(status: str | None) -> str:
    """Normalize provider status strings to the documented uppercase values."""
    return str(status or "").strip().upper()


def infer_extension_from_url(url: str, fallback: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if suffix:
        return suffix
    return fallback.lstrip(".")


def output_path_for_url(default_name: str, output_path: str | None, url: str, fallback_ext: str) -> Path:
    ext = infer_extension_from_url(url, fallback_ext)
    if output_path:
        path = Path(output_path)
        return path if path.suffix else path.with_suffix(f".{ext}")
    return Path(f"{default_name}.{ext}")


class RunningHubClient:
    """Small sync client for RunningHub submit/query/upload/download flows."""

    def __init__(self, api_key: str, base_url: str = RUNNINGHUB_BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def submit(self, endpoint_path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
        import requests

        response = requests.post(
            f"{self.base_url}/{endpoint_path.lstrip('/')}",
            headers=self.headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def query(self, task_id: str, timeout: int = 30) -> dict[str, Any]:
        import requests

        response = requests.post(
            f"{self.base_url}/query",
            headers=self.headers,
            json={"taskId": task_id},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def wait_for_task(
        self,
        task_id: str,
        *,
        poll_interval_seconds: int = 5,
        timeout_seconds: int = 900,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_payload: dict[str, Any] = {}

        while time.time() < deadline:
            last_payload = self.query(task_id)
            status = normalize_runninghub_status(last_payload.get("status"))
            if status == "SUCCESS":
                return last_payload
            if status == "FAILED":
                message = (
                    last_payload.get("errorMessage")
                    or last_payload.get("failedReason")
                    or "RunningHub task failed"
                )
                raise RuntimeError(str(message))
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.time())))

        status = normalize_runninghub_status(last_payload.get("status"))
        raise TimeoutError(f"RunningHub task {task_id} timed out with status {status or 'UNKNOWN'}")

    def upload_file(self, file_path: str, timeout: int = 120) -> str:
        import requests

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content_type, _ = mimetypes.guess_type(path.name)
        with path.open("rb") as f:
            response = requests.post(
                f"{self.base_url}/media/upload/binary",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (path.name, f, content_type or "application/octet-stream")},
                timeout=timeout,
            )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        download_url = data.get("download_url")
        if not download_url:
            raise RuntimeError(f"RunningHub upload response missing download_url: {payload}")
        return str(download_url)

    @staticmethod
    def download(url: str, output_path: Path, timeout: int = 300) -> None:
        import requests

        output_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        output_path.write_bytes(response.content)


def collect_media_urls(
    client: RunningHubClient,
    *,
    url_keys: list[str],
    path_keys: list[str],
    inputs: dict[str, Any],
) -> list[str]:
    """Collect URL inputs and upload local paths for RunningHub media arrays."""
    urls: list[str] = []
    for key in url_keys:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            urls.append(value)
        elif isinstance(value, list):
            urls.extend(str(item) for item in value if str(item))

    for key in path_keys:
        value = inputs.get(key)
        if isinstance(value, str) and value:
            urls.append(client.upload_file(value))
        elif isinstance(value, list):
            for item in value:
                if str(item):
                    urls.append(client.upload_file(str(item)))

    return urls
