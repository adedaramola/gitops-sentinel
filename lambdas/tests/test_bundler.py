"""Unit tests for incident_bundler/app.py"""
import hashlib
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub heavy dependencies so we can import the module without real AWS creds
# ---------------------------------------------------------------------------

# Stub botocore before anything imports it
botocore_stub = types.ModuleType("botocore")
botocore_session_stub = types.ModuleType("botocore.session")
botocore_signers_stub = types.ModuleType("botocore.signers")
botocore_session_stub.get_session = MagicMock()
botocore_signers_stub.RequestSigner = MagicMock()
botocore_stub.session = botocore_session_stub
sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.session", botocore_session_stub)
sys.modules.setdefault("botocore.signers", botocore_signers_stub)

# Stub boto3
boto3_stub = types.ModuleType("boto3")
boto3_stub.client = MagicMock(return_value=MagicMock())
sys.modules.setdefault("boto3", boto3_stub)

# Stub requests + adapters + urllib3
requests_stub = types.ModuleType("requests")
requests_stub.get = MagicMock()
requests_stub.RequestException = Exception
requests_stub.Session = MagicMock(return_value=MagicMock())
requests_adapters_stub = types.ModuleType("requests.adapters")
requests_adapters_stub.HTTPAdapter = MagicMock()
urllib3_stub = types.ModuleType("urllib3")
urllib3_util_stub = types.ModuleType("urllib3.util")
urllib3_retry_stub = types.ModuleType("urllib3.util.retry")
urllib3_retry_stub.Retry = MagicMock()
sys.modules.setdefault("requests", requests_stub)
sys.modules.setdefault("requests.adapters", requests_adapters_stub)
sys.modules.setdefault("urllib3", urllib3_stub)
sys.modules.setdefault("urllib3.util", urllib3_util_stub)
sys.modules.setdefault("urllib3.util.retry", urllib3_retry_stub)

# Set required env vars before import
os.environ.setdefault("INCIDENT_BUCKET", "test-bucket")
os.environ.setdefault("EVENT_BUS_NAME", "test-bus")
os.environ.setdefault("INCIDENTS_TABLE_NAME", "test-table")
os.environ.setdefault("WEBHOOK_SECRET", "")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
import incident_bundler.app as app

importlib.reload(app)  # ensure env vars are picked up


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(request_id="req-1234abcd"):
    ctx = MagicMock()
    ctx.aws_request_id = request_id
    return ctx


def _alertmanager_event(service="svc", env="staging", alertname="HighErrorRate"):
    return {
        "requestContext": {"requestId": "x"},
        "body": json.dumps({
            "alerts": [{
                "labels": {
                    "alertname": alertname,
                    "service": service,
                    "env": env,
                    "severity": "critical",
                },
                "annotations": {"summary": "Error rate high"},
            }]
        }),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDedupKey(unittest.TestCase):
    def test_deterministic(self):
        k1 = app._dedup_key("svc", "staging", "HighErrorRate")
        k2 = app._dedup_key("svc", "staging", "HighErrorRate")
        self.assertEqual(k1, k2)

    def test_different_inputs_produce_different_keys(self):
        k1 = app._dedup_key("svc-a", "staging", "Alert")
        k2 = app._dedup_key("svc-b", "staging", "Alert")
        self.assertNotEqual(k1, k2)

    def test_sha256_format(self):
        k = app._dedup_key("svc", "prod", "Alert")
        self.assertEqual(len(k), 64)


class TestPromQuery(unittest.TestCase):
    def test_skips_when_no_url(self):
        original = app.PROM_URL
        app.PROM_URL = ""
        result = app._prom_query("up")
        self.assertTrue(result.get("skipped"))
        app.PROM_URL = original

    def test_returns_error_on_request_exception(self):
        app.PROM_URL = "http://prom:9090"
        with patch.object(app._SESSION, "get", side_effect=Exception("connection refused")):
            result = app._prom_query("up")
        self.assertIn("error", result)
        app.PROM_URL = ""


class TestWebhookSecretValidation(unittest.TestCase):
    def setUp(self):
        # Patch internal helpers so handler doesn't need real AWS
        self._dedup = patch.object(app, "_dedup_check_and_write", return_value=(True, None))
        self._prom = patch.object(app, "_prom_query", return_value={"skipped": True})
        self._s3 = patch.object(app.s3, "put_object")
        self._emit = patch.object(app, "_emit")
        self._dedup.start()
        self._prom.start()
        self._s3.start()
        self._emit.start()

    def tearDown(self):
        patch.stopall()
        app.WEBHOOK_SECRET = ""

    def test_missing_secret_returns_401(self):
        app.WEBHOOK_SECRET = "correct-secret"
        event = _alertmanager_event()
        event["headers"] = {"x-webhook-secret": "wrong"}
        resp = app.handler(event, _make_context())
        self.assertEqual(resp["statusCode"], 401)

    def test_correct_secret_passes(self):
        app.WEBHOOK_SECRET = "correct-secret"
        event = _alertmanager_event()
        event["headers"] = {"x-webhook-secret": "correct-secret"}
        resp = app.handler(event, _make_context())
        self.assertEqual(resp["statusCode"], 200)

    def test_no_secret_configured_skips_auth(self):
        app.WEBHOOK_SECRET = ""
        event = _alertmanager_event()
        resp = app.handler(event, _make_context())
        self.assertEqual(resp["statusCode"], 200)


class TestHandlerDedup(unittest.TestCase):
    def test_dedup_suppressed_returns_202(self):
        with patch.object(app, "_dedup_check_and_write", return_value=(False, None)):
            event = _alertmanager_event()
            resp = app.handler(event, _make_context())
        self.assertEqual(resp["statusCode"], 202)
        body = json.loads(resp["body"])
        self.assertEqual(body["message"], "dedup_suppressed")


class TestHandlerSuccess(unittest.TestCase):
    def test_stores_bundle_and_returns_200(self):
        with (
            patch.object(app, "_dedup_check_and_write", return_value=(True, None)),
            patch.object(app, "_prom_query", return_value={"skipped": True}),
            patch.object(app.s3, "put_object") as mock_put,
            patch.object(app, "_emit") as mock_emit,
        ):
            event = _alertmanager_event()
            resp = app.handler(event, _make_context())

        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertIn("incident_id", body)
        self.assertIn("s3_key", body)
        mock_put.assert_called_once()
        mock_emit.assert_called_once()

    def test_bundle_s3_key_format(self):
        with (
            patch.object(app, "_dedup_check_and_write", return_value=(True, None)),
            patch.object(app, "_prom_query", return_value={"skipped": True}),
            patch.object(app.s3, "put_object"),
            patch.object(app, "_emit"),
        ):
            event = _alertmanager_event()
            resp = app.handler(event, _make_context())

        body = json.loads(resp["body"])
        self.assertTrue(body["s3_key"].startswith("incidents/inc-"))


if __name__ == "__main__":
    unittest.main()
