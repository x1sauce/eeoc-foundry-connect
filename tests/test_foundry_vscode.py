"""Offline unit tests: no Azure SDK, Azure requests, or Foundry inference."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).parents[1] / "scripts" / "foundry-vscode-sync.py"
spec = importlib.util.spec_from_file_location("vscode_sync", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class DummyCredential:
    def get_token(self, scope):
        assert scope == mod.ARM_SCOPE
        return type("Token", (), {"token": "secret-never-log-this"})()
    def close(self):
        pass

class FoundryVSCodeTests(unittest.TestCase):
    def test_rejects_outside_arm_pagination_host(self):
        with self.assertRaisesRegex(RuntimeError, "host validation"):
            mod.validate_arm_url("https://evil.example/steal")

    def test_token_command_invokes_approved_helper(self):
        command = mod.token_command(r"C:\Users\Test\Python313\python.exe", Path(r"C:\foundry-vscode-auth.py"), None)
        self.assertTrue(command.startswith("!"))
        self.assertIn("foundry-vscode-auth.py", command)
        self.assertIn("token", command)
        self.assertNotIn("az account", command)

    def test_arm_list_pagination(self):
        first = {"value": [{"name": "model1"}], "nextLink": "https://management.azure.com/page2"}
        second = {"value": [{"name": "model2"}]}
        with patch.object(mod, "arm_get", side_effect=[first, second]) as fetch:
            rows = mod.arm_list("https://management.azure.com/page1", DummyCredential())
        self.assertEqual([x["name"] for x in rows], ["model1", "model2"])
        self.assertEqual(fetch.call_count, 2)

    def test_filters_failed_deployments(self):
        rows = [
            {"name": "ready", "properties": {"provisioningState": "Succeeded"}},
            {"name": "broken", "properties": {"provisioningState": "Failed"}},
        ]
        with patch.object(mod, "arm_list", return_value=rows):
            items = mod.deployments_for("11111111-1111-1111-1111-111111111111", "rg", "account", DummyCredential())
        self.assertEqual([r["name"] for r in items], ["ready"])

    def test_arm_group_discovery(self):
        data = [{"name": "aif-eeoc-daes-dev", "id": "/subscriptions/x/resourceGroups/rg-a/providers/Microsoft.CognitiveServices/accounts/aif-eeoc-daes-dev"}]
        with patch.object(mod, "arm_list", return_value=data):
            group = mod.account_group("11111111-1111-1111-1111-111111111111", "aif-eeoc-daes-dev", None, DummyCredential())
        self.assertEqual(group, "rg-a")

    def test_sync_preview_uses_no_az_and_does_not_write(self):
        class FakeLegacy:
            MODELS_YML = Path("/nonexistent-test-config/models.yml")
            yaml = None
            normalize_endpoint = staticmethod(lambda x: x)
            infer_account_name = staticmethod(lambda x: "aif-eeoc-daes-dev")
            build_provider = staticmethod(lambda endpoint, deps: {"apiKey": "!az old", "authHeader": True, "models": [{"id": deps[0]["name"]}]})
            merge_document = staticmethod(lambda provider: {"providers": {"foundry": provider}})
            write_models = staticmethod(lambda document, *, dry_run: self.assertTrue(dry_run))

        rows = [{"name": "approved-model", "properties": {"provisioningState": "Succeeded"}}]
        with (patch.object(mod, "legacy_sync", return_value=FakeLegacy()),
              patch.object(mod, "create_credential", return_value=DummyCredential()),
              patch.object(mod, "account_group", return_value="rg"),
              patch.object(mod, "deployments_for", return_value=rows)):
            mod.sync(endpoint=mod.DEFAULT_ENDPOINT, subscription_id="11111111-1111-1111-1111-111111111111", resource_group="rg", tenant_id=None, apply=False)

    def test_prevent_empty_deployments_overwrite(self):
        with patch.object(mod, "arm_list", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                mod.deployments_for("11111111-1111-1111-1111-111111111111", "rg", "account", DummyCredential())

if __name__ == "__main__":
    unittest.main()
