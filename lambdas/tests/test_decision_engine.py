"""Unit tests for decision_engine/app.py"""
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub dependencies before import
# ---------------------------------------------------------------------------

boto3_stub = types.ModuleType("boto3")
boto3_stub.client = MagicMock(return_value=MagicMock())
sys.modules.setdefault("boto3", boto3_stub)

requests_stub = types.ModuleType("requests")
requests_stub.request = MagicMock()
requests_stub.post = MagicMock()
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

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = MagicMock(return_value={})
sys.modules.setdefault("yaml", yaml_stub)

os.environ.setdefault("GITHUB_OWNER", "test-org")
os.environ.setdefault("GITHUB_REPO", "test-repo")
os.environ.setdefault("GITHUB_APP_TOKEN_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:gh")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
import decision_engine.app as app

importlib.reload(app)


# ---------------------------------------------------------------------------
# Tests: pure functions (no AWS/GitHub calls)
# ---------------------------------------------------------------------------

KUSTOMIZE_WITH_REPLICAS = """\
patches:
  - patch: |-
      - op: replace
        path: /spec/replicas
        value: 2
    target:
      kind: Deployment
"""

KUSTOMIZE_WITHOUT_REPLICAS = """\
namePrefix: staging-
"""

DEPLOYMENT_YAML = """\
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: app
          image: ghcr.io/org/app:v1.2.3
"""


class TestPatchReplicasKustomize(unittest.TestCase):
    def test_replaces_value_line(self):
        result = app._patch_replicas_kustomize(KUSTOMIZE_WITH_REPLICAS, 5)
        self.assertIn("value: 5", result)
        self.assertNotIn("value: 2", result)

    def test_only_first_match_replaced(self):
        yaml_two_values = KUSTOMIZE_WITH_REPLICAS + "        value: 99\n"
        result = app._patch_replicas_kustomize(yaml_two_values, 3)
        self.assertEqual(result.count("value: 3"), 1)
        self.assertIn("value: 99", result)

    def test_raises_when_no_value_line(self):
        with self.assertRaises(ValueError):
            app._patch_replicas_kustomize(KUSTOMIZE_WITHOUT_REPLICAS, 3)

    def test_ends_with_newline(self):
        result = app._patch_replicas_kustomize(KUSTOMIZE_WITH_REPLICAS, 2)
        self.assertTrue(result.endswith("\n"))


class TestPatchImageDeployment(unittest.TestCase):
    def test_replaces_tag(self):
        result = app._patch_image_deployment(DEPLOYMENT_YAML, "v2.0.0")
        self.assertIn("image: ghcr.io/org/app:v2.0.0", result)
        self.assertNotIn(":v1.2.3", result)

    def test_no_change_when_no_image(self):
        yaml_no_image = "kind: Service\n"
        result = app._patch_image_deployment(yaml_no_image, "v2.0.0")
        self.assertEqual(result, yaml_no_image)


class TestChooseActionHeuristic(unittest.TestCase):
    def _allowed(self, *actions):
        return {"allowed_actions": [{"action": a} for a in actions]}

    def test_prefers_rollback_on_5xx_data(self):
        bundle = {
            "env": "staging",
            "prometheus": {"error_rate_5xx": {"data": {"result": [{"value": [0, "0.5"]}]}}},
        }
        allowed = self._allowed("rollback_image", "scale_replicas")
        plan = app._choose_action_heuristic(bundle, allowed)
        self.assertEqual(plan["action"], "rollback_image")

    def test_falls_back_to_scale(self):
        bundle = {"env": "staging", "prometheus": {}}
        allowed = self._allowed("scale_replicas")
        plan = app._choose_action_heuristic(bundle, allowed)
        self.assertEqual(plan["action"], "scale_replicas")

    def test_falls_back_to_restart(self):
        bundle = {"env": "staging", "prometheus": {}}
        plan = app._choose_action_heuristic(bundle, {"allowed_actions": []})
        self.assertEqual(plan["action"], "restart_rollout")


class TestLlmPlanFallback(unittest.TestCase):
    """LLM plan should fall back to heuristic on any exception."""

    def _bundle(self):
        return {"incident_id": "inc-1", "env": "staging", "service": "svc", "prometheus": {}}

    def _allowed(self):
        return {"allowed_actions": [{"action": "scale_replicas"}, {"action": "rollback_image"}]}

    def test_falls_back_when_bedrock_raises(self):
        app.MODEL_PROVIDER = "bedrock"
        app.bedrock.invoke_model = MagicMock(side_effect=Exception("throttled"))
        plan = app._llm_plan(self._bundle(), self._allowed())
        self.assertIn(plan["action"], ["scale_replicas", "rollback_image", "restart_rollout"])
        self.assertEqual(plan["rationale"], "Fallback heuristic plan.")

    def test_falls_back_on_disallowed_action(self):
        app.MODEL_PROVIDER = "bedrock"
        mock_resp = MagicMock()
        mock_resp["body"].read.return_value = json.dumps({
            "content": [{"text": json.dumps({
                "action": "delete_cluster",  # not in allowed list
                "target": {"service": "svc", "env": "staging"},
                "params": {},
                "risk": "high",
                "rationale": "nope",
            })}]
        }).encode()
        app.bedrock.invoke_model = MagicMock(return_value=mock_resp)
        plan = app._llm_plan(self._bundle(), self._allowed())
        self.assertNotEqual(plan["action"], "delete_cluster")


class TestPatchImageEdgeCases(unittest.TestCase):
    """Edge cases specific to the YAML-based _patch_image_deployment."""

    def test_registry_with_port_preserves_base(self):
        # rsplit(":", 1) must not split on the registry port
        yaml_with_port = """\
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: app
          image: registry.example.com:5000/org/app:v1.0.0
"""
        result = app._patch_image_deployment(yaml_with_port, "v2.0.0")
        self.assertIn("registry.example.com:5000/org/app:v2.0.0", result)
        self.assertNotIn(":v1.0.0", result)

    def test_no_image_field_returns_valid_yaml(self):
        yaml_no_image = "kind: Service\nmetadata:\n  name: svc\n"
        result = app._patch_image_deployment(yaml_no_image, "v2.0.0")
        # Should not raise and should return parseable YAML
        import yaml as _yaml
        doc = _yaml.safe_load(result)
        self.assertEqual(doc["kind"], "Service")

    def test_no_image_field_unchanged(self):
        yaml_no_image = "kind: Service\n"
        result = app._patch_image_deployment(yaml_no_image, "v2.0.0")
        self.assertNotIn("v2.0.0", result)


class TestPatchReplicasEdgeCases(unittest.TestCase):
    """Edge cases specific to the YAML-based _patch_replicas_kustomize."""

    _KUSTOMIZE_MULTI_PATCH = """\
patches:
  - patch: |-
      - op: replace
        path: /spec/replicas
        value: 2
    target:
      kind: Deployment
  - patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/memory
        value: 512Mi
    target:
      kind: Deployment
"""

    def test_only_replicas_patch_is_updated(self):
        result = app._patch_replicas_kustomize(self._KUSTOMIZE_MULTI_PATCH, 7)
        self.assertIn("value: 7", result)
        # Memory patch should be untouched
        self.assertIn("512Mi", result)

    def test_raises_when_no_replicas_op(self):
        kustomize_no_replicas = """\
patches:
  - patch: |-
      - op: replace
        path: /metadata/labels/version
        value: v2
    target:
      kind: Deployment
"""
        with self.assertRaises(ValueError):
            app._patch_replicas_kustomize(kustomize_no_replicas, 5)

    def test_output_is_valid_yaml(self):
        import yaml as _yaml
        result = app._patch_replicas_kustomize(KUSTOMIZE_WITH_REPLICAS, 4)
        # Should not raise
        _yaml.safe_load(result)


if __name__ == "__main__":
    unittest.main()
