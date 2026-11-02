import os
from pathlib import Path

from app.core.config import Settings


def test_settings_uses_repository_env_file_and_environment_precedence(monkeypatch):
    root_env = Path(__file__).resolve().parents[2] / ".env"
    assert Settings.model_config["env_file"] == root_env
    monkeypatch.setenv("ADMIN_API_KEY", "process-value")
    assert Settings().admin_api_key == "process-value"
