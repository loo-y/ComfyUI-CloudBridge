import json
import unittest
from collections import deque

import requests

from cloudbridge.providers.kie import (
    CREATE_TASK_URL,
    MODEL_ID,
    TASK_STATUS_URL,
    UPLOAD_URL,
    KieAPIError,
    KieClient,
)
from cloudbridge.utils.images import EncodedImage


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, post_responses=(), get_responses=()):
        self.post_responses = deque(post_responses)
        self.get_responses = deque(get_responses)
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        response = self.post_responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        response = self.get_responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def client_with(session, **kwargs):
    return KieClient(
        "secret-test-key",
        session=session,
        poll_delays=(0,),
        sleep=lambda _delay: None,
        **kwargs,
    )


class KieClientTests(unittest.TestCase):
    def test_uploads_binary_image_and_returns_download_url(self):
        session = FakeSession(
            post_responses=[
                FakeResponse(
                    payload={
                        "success": True,
                        "code": 200,
                        "data": {"downloadUrl": "https://files.example/input.png"},
                    }
                )
            ]
        )
        client = client_with(session)

        result = client.upload_image(EncodedImage("input.png", b"png", "image/png"))

        self.assertEqual(result, "https://files.example/input.png")
        url, call = session.post_calls[0]
        self.assertEqual(url, UPLOAD_URL)
        self.assertEqual(call["files"]["file"], ("input.png", b"png", "image/png"))
        self.assertEqual(call["headers"]["Authorization"], "Bearer secret-test-key")

    def test_creates_expected_seedream_payload_without_callback(self):
        session = FakeSession(
            post_responses=[
                FakeResponse(
                    payload={"code": 200, "msg": "success", "data": {"taskId": "task-1"}}
                )
            ]
        )
        client = client_with(session)

        with self.assertLogs("cloudbridge.providers.kie", level="INFO") as logs:
            task_id = client.create_seedream_task(
                prompt="Edit this image",
                image_urls=["https://files.example/input.png"],
                aspect_ratio="1:1",
                quality="basic",
                output_format="png",
                nsfw_checker=False,
            )

        self.assertEqual(task_id, "task-1")
        self.assertIn("task_id=task-1", logs.output[0])
        url, call = session.post_calls[0]
        self.assertEqual(url, CREATE_TASK_URL)
        self.assertEqual(call["json"]["model"], MODEL_ID)
        self.assertNotIn("callBackUrl", call["json"])
        self.assertEqual(call["json"]["input"]["image_urls"], ["https://files.example/input.png"])

    def test_waits_through_pending_states_and_parses_success(self):
        session = FakeSession(
            get_responses=[
                FakeResponse(payload={"code": 200, "data": {"state": "waiting"}}),
                FakeResponse(payload={"code": 200, "data": {"state": "generating"}}),
                FakeResponse(
                    payload={
                        "code": 200,
                        "data": {
                            "state": "success",
                            "resultJson": json.dumps(
                                {"resultUrls": ["https://result.example/image.png"]}
                            ),
                        },
                    }
                ),
            ]
        )

        result = client_with(session).wait_for_task("task-1")

        self.assertEqual(result.task_id, "task-1")
        self.assertEqual(result.result_urls, ["https://result.example/image.png"])
        self.assertTrue(all(call[0] == TASK_STATUS_URL for call in session.get_calls))

    def test_logs_remote_progress_when_available(self):
        session = FakeSession(
            get_responses=[
                FakeResponse(
                    payload={
                        "code": 200,
                        "data": {
                            "state": "success",
                            "progress": 100,
                            "resultJson": {"resultUrls": ["https://result.example/image.png"]},
                        },
                    }
                )
            ]
        )

        with self.assertLogs("cloudbridge.providers.kie", level="INFO") as logs:
            client_with(session).wait_for_task("task-progress")

        self.assertIn("state=success", logs.output[0])
        self.assertIn("progress=100%", logs.output[0])
        self.assertIn("elapsed=0s", logs.output[0])

    def test_retries_transient_poll_response(self):
        session = FakeSession(
            get_responses=[
                FakeResponse(status_code=429, payload={"code": 429}),
                FakeResponse(
                    payload={
                        "code": 200,
                        "data": {
                            "state": "success",
                            "resultJson": {"resultUrls": ["https://result.example/image.png"]},
                        },
                    }
                ),
            ]
        )

        result = client_with(session).wait_for_task("task-1")

        self.assertEqual(len(session.get_calls), 2)
        self.assertEqual(result.result_urls, ["https://result.example/image.png"])

    def test_reports_remote_generation_failure(self):
        session = FakeSession(
            get_responses=[
                FakeResponse(
                    payload={
                        "code": 200,
                        "data": {
                            "state": "fail",
                            "failCode": "CONTENT",
                            "failMsg": "Rejected",
                        },
                    }
                )
            ]
        )

        with self.assertRaisesRegex(KieAPIError, "CONTENT.*Rejected"):
            client_with(session).wait_for_task("task-1")

    def test_does_not_retry_ambiguous_task_creation_failure(self):
        session = FakeSession(post_responses=[requests.Timeout("timed out")])

        with self.assertRaisesRegex(KieAPIError, "not retried"):
            client_with(session).create_seedream_task(
                "prompt", ["https://example/input.png"], "1:1", "basic", "png", False
            )

        self.assertEqual(len(session.post_calls), 1)

    def test_api_error_does_not_include_api_key(self):
        session = FakeSession(
            post_responses=[FakeResponse(payload={"code": 402, "msg": "No credits"})]
        )

        with self.assertRaises(KieAPIError) as caught:
            client_with(session).create_seedream_task(
                "prompt", ["https://example/input.png"], "1:1", "basic", "png", False
            )

        self.assertIn("insufficient credits", str(caught.exception))
        self.assertNotIn("secret-test-key", str(caught.exception))

    def test_rejects_malformed_json_response(self):
        session = FakeSession(post_responses=[FakeResponse(payload=ValueError("bad json"))])

        with self.assertRaisesRegex(KieAPIError, "invalid JSON"):
            client_with(session).create_seedream_task(
                "prompt", ["https://example/input.png"], "1:1", "basic", "png", False
            )

    def test_reports_poll_timeout(self):
        session = FakeSession()
        client = client_with(session, max_wait_seconds=0)

        with self.assertRaisesRegex(KieAPIError, "did not finish"):
            client.wait_for_task("task-timeout")

    def test_download_retries_then_returns_content(self):
        session = FakeSession(
            get_responses=[
                FakeResponse(status_code=500),
                FakeResponse(status_code=200, content=b"image-data"),
            ]
        )

        content = client_with(session).download_image("https://result.example/image.png")

        self.assertEqual(content, b"image-data")
        self.assertEqual(len(session.get_calls), 2)


if __name__ == "__main__":
    unittest.main()
