import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "foundry-connect.py"
spec = importlib.util.spec_from_file_location("foundry_connect", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FoundryConnectTests(unittest.TestCase):
    def test_infer_account_name(self):
        self.assertEqual(
            mod.infer_account_name("https://aif-eeoc-daes-dev.services.ai.azure.com"),
            "aif-eeoc-daes-dev",
        )

    def test_token_command_uses_entra_resource(self):
        self.assertIn("https://ai.azure.com", mod.TOKEN_COMMAND)
        self.assertIn("get-access-token", mod.TOKEN_COMMAND)


if __name__ == "__main__":
    unittest.main()
