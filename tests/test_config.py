# tests/test_config.py
import os
import pytest
from config import get_env

def test_get_env_returns_value(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "test_value")
    assert get_env("TEST_KEY") == "test_value"

def test_get_env_raises_on_missing():
    with pytest.raises(ValueError, match="Missing required env var"):
        get_env("NONEXISTENT_VAR_12345")
