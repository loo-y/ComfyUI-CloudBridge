from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import requests

from ..utils.images import EncodedImage


UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"
CREATE_TASK_URL = "https://api.kie.ai/api/v1/jobs/createTask"
TASK_STATUS_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"
MODEL_ID = "seedream/5-lite-image-to-image"
PENDING_STATES = {"waiting", "queuing", "generating"}
ERROR_LABELS = {
    401: "authentication failed",
    402: "insufficient credits",
    404: "resource not found",
    422: "request validation failed",
    429: "rate limit exceeded",
    433: "API key usage limit exceeded",
    455: "service unavailable for maintenance",
    500: "server error",
    501: "generation failed",
    505: "feature disabled",
}


class KieAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class KieTaskResult:
    task_id: str
    result_urls: list[str]


class KieClient:
    def __init__(
        self,
        api_key: str,
        session: requests.Session | None = None,
        poll_delays: Sequence[float] = (2, 3, 5, 8, 10),
        max_wait_seconds: float = 15 * 60,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A Kie API key is required.")
        self._api_key = api_key.strip()
        self._session = session or requests.Session()
        self._poll_delays = tuple(poll_delays)
        self._max_wait_seconds = max_wait_seconds
        self._sleep = sleep
        self._monotonic = monotonic

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @property
    def _json_headers(self) -> dict[str, str]:
        return {**self._auth_headers, "Content-Type": "application/json"}

    def upload_image(self, image: EncodedImage) -> str:
        try:
            response = self._session.post(
                UPLOAD_URL,
                headers=self._auth_headers,
                files={"file": (image.filename, image.content, image.mime_type)},
                data={"uploadPath": "images/cloudbridge", "fileName": image.filename},
                timeout=(10, 120),
            )
        except requests.RequestException as exc:
            raise KieAPIError(f"Kie image upload failed: {exc}") from exc

        payload = self._parse_response(response, "image upload")
        data = payload.get("data") or {}
        file_url = data.get("downloadUrl") or data.get("fileUrl")
        if (
            payload.get("code") != 200
            or not payload.get("success", True)
            or not isinstance(file_url, str)
        ):
            raise self._api_error("image upload", payload)
        return file_url

    def create_seedream_task(
        self,
        prompt: str,
        image_urls: Sequence[str],
        aspect_ratio: str,
        quality: str,
        output_format: str,
        nsfw_checker: bool,
    ) -> str:
        request_payload = {
            "model": MODEL_ID,
            "input": {
                "prompt": prompt,
                "image_urls": list(image_urls),
                "aspect_ratio": aspect_ratio,
                "quality": quality,
                "output_format": output_format,
                "nsfw_checker": nsfw_checker,
            },
        }
        try:
            response = self._session.post(
                CREATE_TASK_URL,
                headers=self._json_headers,
                json=request_payload,
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            raise KieAPIError(
                "Kie task creation failed. The request is not retried automatically "
                "because a retry could create a second billable task. "
                f"Details: {exc}"
            ) from exc

        payload = self._parse_response(response, "task creation")
        self._require_api_success("task creation", payload)
        task_id = (payload.get("data") or {}).get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise KieAPIError("Kie task creation succeeded without returning a task ID.")
        return task_id

    def wait_for_task(self, task_id: str) -> KieTaskResult:
        start = self._monotonic()
        delay_index = 0
        last_transport_error: str | None = None

        while self._monotonic() - start < self._max_wait_seconds:
            try:
                response = self._session.get(
                    TASK_STATUS_URL,
                    headers=self._auth_headers,
                    params={"taskId": task_id},
                    timeout=(10, 30),
                )
            except requests.RequestException as exc:
                last_transport_error = str(exc)
                self._wait(delay_index)
                delay_index += 1
                continue

            if response.status_code == 429 or response.status_code >= 500:
                last_transport_error = f"HTTP {response.status_code}"
                self._wait(delay_index)
                delay_index += 1
                continue

            payload = self._parse_response(response, "task status")
            self._require_api_success("task status", payload)
            data = payload.get("data") or {}
            state = data.get("state")

            if state in PENDING_STATES:
                self._wait(delay_index)
                delay_index += 1
                continue
            if state == "fail":
                fail_code = data.get("failCode") or "unknown"
                fail_message = data.get("failMsg") or payload.get("msg") or "unknown error"
                raise KieAPIError(
                    f"Kie generation failed [{fail_code}]: {fail_message}"
                )
            if state == "success":
                result_urls = self._extract_result_urls(data.get("resultJson"))
                return KieTaskResult(task_id=task_id, result_urls=result_urls)
            raise KieAPIError(f"Kie returned an unknown task state: {state!r}.")

        suffix = f" Last transport error: {last_transport_error}." if last_transport_error else ""
        raise KieAPIError(
            f"Kie task {task_id} did not finish within "
            f"{self._max_wait_seconds:g} seconds.{suffix}"
        )

    def download_image(self, url: str) -> bytes:
        last_error: str | None = None
        for attempt, delay in enumerate((1, 2, 4), start=1):
            try:
                response = self._session.get(url, timeout=(10, 120))
                if response.status_code == 200:
                    return response.content
                last_error = f"HTTP {response.status_code}"
                if response.status_code < 500 and response.status_code != 429:
                    break
            except requests.RequestException as exc:
                last_error = str(exc)
            if attempt < 3:
                self._sleep(delay)
        raise KieAPIError(f"Failed to download a Kie result image: {last_error}.")

    def _wait(self, delay_index: int) -> None:
        if not self._poll_delays:
            return
        self._sleep(self._poll_delays[min(delay_index, len(self._poll_delays) - 1)])

    @staticmethod
    def _extract_result_urls(result_json: Any) -> list[str]:
        if isinstance(result_json, str):
            try:
                result_json = json.loads(result_json)
            except json.JSONDecodeError as exc:
                raise KieAPIError("Kie returned malformed result JSON.") from exc
        if not isinstance(result_json, dict):
            raise KieAPIError("Kie completed the task without result metadata.")
        urls = result_json.get("resultUrls")
        if not isinstance(urls, list) or not urls or not all(
            isinstance(url, str) and url for url in urls
        ):
            raise KieAPIError("Kie completed the task without result URLs.")
        return urls

    @staticmethod
    def _parse_response(response: requests.Response, stage: str) -> dict[str, Any]:
        if not 200 <= response.status_code < 300:
            raise KieAPIError(f"Kie {stage} failed with HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise KieAPIError(f"Kie {stage} returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise KieAPIError(f"Kie {stage} returned an unexpected response shape.")
        return payload

    @classmethod
    def _require_api_success(cls, stage: str, payload: dict[str, Any]) -> None:
        if payload.get("code") != 200:
            raise cls._api_error(stage, payload)

    @staticmethod
    def _api_error(stage: str, payload: dict[str, Any]) -> KieAPIError:
        code = payload.get("code", "unknown")
        label = ERROR_LABELS.get(code, "API error")
        message = payload.get("msg") or "No error message returned"
        return KieAPIError(f"Kie {stage} failed [{code}: {label}]: {message}")
