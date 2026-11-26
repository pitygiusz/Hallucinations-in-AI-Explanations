"""Offline tests for local configuration and model selection."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import judge_common as shared


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / ".env").write_text(
            "OPENAI_API_KEY='literal-${NOT_EXPANDED}'\n"
            "OPENAI_MODEL_ID=openai-from-file\n"
            "GOOGLE_API_KEY=google-from-file\n"
            "GOOGLE_MODEL_ID=google-model-from-file\n")
        self.root_patch = patch.object(shared, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_env_file_is_loaded_literally_without_replacing_shell_values(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "shell-key"}, clear=True):
            shared.load_environment()
            self.assertEqual(os.environ["GOOGLE_API_KEY"], "shell-key")
            self.assertEqual(os.environ["OPENAI_API_KEY"], "literal-${NOT_EXPANDED}")
            self.assertEqual(os.environ["GOOGLE_MODEL_ID"], "google-model-from-file")

    def test_both_provider_models_default_from_file(self):
        for provider, expected in [("openai", "openai-from-file"), ("google", "google-model-from-file")]:
            with patch.dict(os.environ, {}, clear=True), patch("sys.argv", [
                    "judge", "prepare", "results.json", "--run", "run"]):
                self.assertEqual(shared.parse_args(provider).model, expected)

    def test_cli_model_overrides_shell_and_file(self):
        with patch.dict(os.environ, {"GOOGLE_MODEL_ID": "shell-model"}, clear=True):
            with patch("sys.argv", ["judge", "prepare", "results.json", "--run", "run"]):
                self.assertEqual(shared.parse_args("google").model, "shell-model")
            with patch("sys.argv", ["judge", "prepare", "results.json", "--run", "run", "--model", "cli-model"]):
                self.assertEqual(shared.parse_args("google").model, "cli-model")

    def test_missing_google_model_is_reported_before_preparing(self):
        (self.root / ".env").write_text("GOOGLE_MODEL_ID=\n")
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", [
                "judge", "prepare", "results.json", "--run", "run"]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                shared.parse_args("google")
        self.assertEqual(failure.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
