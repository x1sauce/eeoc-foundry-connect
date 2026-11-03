import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "foundry-sync.py"
spec = importlib.util.spec_from_file_location("foundry_sync", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FoundrySyncTests(unittest.TestCase):
    def test_infer_account_name(self):
        self.assertEqual(
            mod.infer_account_name("https://aif-eeoc-daes-dev.services.ai.azure.com"),
            "aif-eeoc-daes-dev",
        )

    def test_provider_uses_bearer_auth(self):
        deployments = [
            {
                "name": "gpt-4o-prod",
                "properties": {
                    "provisioningState": "Succeeded",
                    "model": {"name": "gpt-4o"},
                },
            }
        ]
        provider = mod.build_provider("https://aif-eeoc-daes-dev.services.ai.azure.com", deployments)
        self.assertEqual(provider["api"], "openai-responses")
        self.assertTrue(provider["authHeader"])
        self.assertIn("az account get-access-token", provider["apiKey"])
        self.assertEqual(provider["models"][0]["id"], "gpt-4o-prod")
        self.assertEqual(provider["models"][0]["name"], "gpt-4o (Foundry)")

    def test_model_metadata_uses_underlying_model_name(self):
        deployments = [
            {
                "name": "production-coder",
                "properties": {
                    "provisioningState": "Succeeded",
                    "model": {"name": "gpt-5.6-sol"},
                },
            }
        ]
        provider = mod.build_provider("https://aif-eeoc-daes-dev.services.ai.azure.com", deployments)
        model = provider["models"][0]
        self.assertTrue(model["reasoning"])
        self.assertEqual(model["contextWindow"], 400_000)


if __name__ == "__main__":
    unittest.main()
