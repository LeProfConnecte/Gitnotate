"""Réglages IA V3 : secrets privés, sauvegarde atomique et tests API sans génération.

Toutes les réponses HTTP sont simulées. Ne jamais lire ou écrire le .env réel.
"""
from pathlib import Path

import pytest

import ai_settings_v3 as setting


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload if payload is not None else {
            "data": [{"id": "test-provider-model"}, {"id": "openrouter/free"}]}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, status=200, model="test-provider-model"):
        self.status = status
        self.model = model
        self.calls = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls.append((url, headers, timeout, allow_redirects))
        if self.status != 200:
            return FakeResponse(status=self.status)
        if url.endswith("/key"):
            return FakeResponse(payload={"data": {"limit": 100, "usage": 0}})
        return FakeResponse(payload={"data": [
            {"id": self.model}, {"id": "openrouter/free"}]})


@pytest.fixture
def private_env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# Keep this comment and Notion secrets unchanged\n"
        "NOTION_READONLY_TOKEN=ntn_NOT_A_REAL_KEY_12345\n"
        "DATABASE_ID=0123456789abcdef0123456789abcdef\n"
        "MISTRAL_API_KEY=fake-mistral-key-123\n"
        "MISTRAL_MODEL=mistral-small-2603\n"
        "OPENAI_API_KEY=old-test-openai-key-12345\n"
        "OPENAI_MODEL=gpt-6.1-terra\n"
        "LLM_PROVIDERS=mistral,openrouter\n"
        "OTHER_CUSTOM_SETTING=keep-me\n",
        encoding="utf-8")
    return path


def test_settings_status_never_returns_stored_secret(private_env):
    data = setting.status(private_env)
    assert len(data) == 4
    assert [p["id"] for p in data] == list(setting.PROVIDERS)
    openai = next(p for p in data if p["id"] == "openai")
    assert openai["key_configured"] is True
    assert openai["model"] == "gpt-6.1-terra"
    assert next(p for p in data if p["id"] == "anthropic")["key_configured"] is False
    assert "old-test-openai-key-12345" not in str(data)
    assert "ntn_NOT_A_REAL_KEY_12345" not in str(data)


def test_atomic_save_model_only_preserves_other_variables(private_env):
    original = private_env.read_text(encoding="utf-8")
    response = setting.save(private_env, "openai", "gpt-6.2-sol")
    updated = private_env.read_text(encoding="utf-8")
    assert response["restart_required"] is True
    assert "OPENAI_MODEL=gpt-6.2-sol" in updated
    assert "OPENAI_API_KEY=old-test-openai-key-12345" in updated
    for line in (
        "NOTION_READONLY_TOKEN=ntn_NOT_A_REAL_KEY_12345",
        "DATABASE_ID=0123456789abcdef0123456789abcdef",
        "MISTRAL_API_KEY=fake-mistral-key-123",
        "LLM_PROVIDERS=mistral,openrouter",
        "OTHER_CUSTOM_SETTING=keep-me",
        "# Keep this comment and Notion secrets unchanged",
    ):
        assert line in original and line in updated
    assert not list(private_env.parent.glob(".ai-settings-*.tmp"))
    second = setting.save(private_env, "openai", "gpt-6.2-sol")
    assert second["restart_required"] is False
    assert private_env.read_text(encoding="utf-8") == updated


def test_replace_and_explicit_clear_key(private_env):
    response = setting.save(
        private_env, "openai", "gpt-6.1-terra", "sk-proj-fake-test-ABCDEFGHI")
    text = private_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-proj-fake-test-ABCDEFGHI" in text
    assert response["key_configured"] is True
    assert "sk-proj-fake-test-ABCDEFGHI" not in str(response)
    cleared = setting.save(private_env, "openai", "gpt-6.1-terra", clear_key=True)
    after = private_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=\n" in after
    assert "NOTION_READONLY_TOKEN=ntn_NOT_A_REAL_KEY_12345" in after
    assert cleared["key_configured"] is False


def test_add_new_provider_when_no_existing_line(private_env):
    response = setting.save(
        private_env, "anthropic", "claude-sonnet-5-5",
        secret="sk-ant-test-value-ABCDEFGHI")
    assert response["key_configured"] is True
    text = private_env.read_text(encoding="utf-8")
    assert text.count("ANTHROPIC_MODEL=") == 1
    assert text.count("ANTHROPIC_API_KEY=") == 1
    assert "OTHER_CUSTOM_SETTING=keep-me\n" in text


def test_preserve_crlf_bom_and_comments(tmp_path):
    path = tmp_path / ".env"
    initial = (
        b"\xef\xbb\xbf# TEST\r\nNOTION_READONLY_TOKEN=ntn_example_key\r\n"
        b"OPENAI_MODEL=gpt-6-luna\r\nOPENAI_API_KEY=sk-test-existing\r\n")
    path.write_bytes(initial)
    setting.save(path, "openai", "gpt-6.1-terra")
    saved = path.read_bytes()
    assert saved.startswith(b"\xef\xbb\xbf")
    assert b"\r\nNOTION_READONLY_TOKEN=ntn_example_key\r\n" in saved
    assert b"OPENAI_MODEL=gpt-6.1-terra\r\n" in saved
    assert b"OPENAI_API_KEY=sk-test-existing\r\n" in saved


@pytest.mark.parametrize("model", [
    "x\nNOTION_READONLY_TOKEN=attacker", "x # inline comment", '"quoted"',
    "../../foo", " ", "some model", "x\x00y",
])
def test_invalid_model_does_not_touch_env(private_env, model):
    before = private_env.read_bytes()
    with pytest.raises(setting.SettingsError):
        setting.save(private_env, "openai", model, secret="fake-openai-key-12345")
    assert private_env.read_bytes() == before


@pytest.mark.parametrize("key", [
    "abc\nNOTION_READONLY_TOKEN=attacker", " key", "key # comment",
    '"quoted"', "short", "test\x00key", "key\\with\\separator",
])
def test_invalid_key_does_not_touch_env(private_env, key):
    original = private_env.read_bytes()
    with pytest.raises(setting.SettingsError):
        setting.save(private_env, "mistral", "mistral-small-2603", secret=key)
    assert private_env.read_bytes() == original


def test_unknown_provider_and_duplicate_env_rejected(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OPENAI_MODEL=first\nOPENAI_MODEL=second\n", encoding="utf-8")
    with pytest.raises(setting.SettingsError, match="dupliquée"):
        setting.save(path, "openai", "gpt-6.2-sol")
    with pytest.raises(setting.SettingsError, match="inconnu"):
        setting.save(path, "notion", "gpt-6.2-sol")
    assert path.read_text(encoding="utf-8") == "OPENAI_MODEL=first\nOPENAI_MODEL=second\n"


def test_atomic_failure_keeps_old_bytes(private_env, monkeypatch):
    before = private_env.read_bytes()
    def failed_replace(*args, **kwargs):
        raise OSError("fake replace failure")
    monkeypatch.setattr(setting.os, "replace", failed_replace)
    with pytest.raises(setting.SettingsError, match="atomique"):
        setting.save(private_env, "openai", "gpt-6.2-sol")
    assert private_env.read_bytes() == before
    assert not list(private_env.parent.glob(".ai-settings-*.tmp"))


def test_check_four_provider_models_over_https_only(private_env):
    for provider in setting.PROVIDERS:
        fake = FakeSession()
        result = setting.check_connection(
            private_env, provider, "test-provider-model",
            secret="fake-provider-test-key-123456", session=fake)
        assert result["key_accepted"] is True
        assert result["model_listed"] is True
        assert result["no_generation"] is True
        assert all(url.startswith("https://") for url, *_ in fake.calls)
        assert all("/v1/models" in url or url.endswith("/v1/key")
                   for url, *_ in fake.calls)
        assert all(not allow_redirects for _, _, _, allow_redirects in fake.calls)
        assert all(t == 15 for _, _, t, _ in fake.calls)
        assert "fake-provider-test-key-123456" not in str(result)
        assert len(fake.calls) == (2 if provider == "openrouter" else 1)


def test_openrouter_models_public_not_enough_for_auth(private_env):
    fake = FakeSession(status=401)
    with pytest.raises(setting.SettingsError, match="401"):
        setting.check_connection(private_env, "openrouter", "openrouter/free",
                                 secret="fake-router-test-key-123456", session=fake)
    assert len(fake.calls) == 1
    assert fake.calls[0][0].endswith("/api/v1/key")


def test_redirects_and_quota_refused(private_env):
    for status in (302, 429):
        fake = FakeSession(status=status)
        with pytest.raises(setting.SettingsError):
            setting.check_connection(private_env, "openai", "gpt-6.1-terra",
                                     secret="fake-openai-test-key-123456",
                                     session=fake)


def test_key_configured_without_model_not_a_real_generation(private_env):
    fake = FakeSession()
    data = setting.check_connection(private_env, "openai", "gpt-unknown-model",
                                    session=fake)
    assert data["key_accepted"] is True
    assert data["model_listed"] is False
    assert data["model_check"] == "not_listed"


def test_no_network_until_requested(private_env, monkeypatch):
    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("Unexpected provider request")
    before = private_env.read_bytes()
    setting.status(private_env)
    setting.save(private_env, "openai", "gpt-6.1-terra")
    assert private_env.read_bytes() == before
    with pytest.raises(AssertionError):
        setting.check_connection(private_env, "openai", "gpt-6.1-terra",
                                 session=NoNetwork())
