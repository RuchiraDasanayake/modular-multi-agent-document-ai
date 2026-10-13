from __future__ import annotations

from types import SimpleNamespace

from idpo.agents import extraction_providers


def test_custom_openai_compatible_endpoint_uses_configured_model_and_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs: object) -> SimpleNamespace:
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"entities":[]}'))],
                usage=SimpleNamespace(prompt_tokens=7, completion_tokens=4, total_tokens=11),
            )

    monkeypatch.setattr(extraction_providers, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(extraction_providers, "OpenAI", FakeOpenAI)

    content, meta = extraction_providers.openai_chat_completion(
        model_name="example-chat-model",
        prompt="Extract an example field.",
        api_key="iba_" + "x" * 32,
        base_url="https://icore.example.test/innobot-api/v1",
        timeout_s=10,
        temperature=0.0,
        max_tokens=64,
        response_format=None,
        retry_without_json_mode=False,
    )

    assert captured["client"]["base_url"] == "https://icore.example.test/innobot-api/v1"
    assert captured["client"]["api_key"] == "iba_" + "x" * 32
    assert captured["request"]["model"] == "example-chat-model"
    assert captured["request"]["max_tokens"] == 64
    assert content == '{"entities":[]}'
    assert meta["total_tokens"] == 11


def test_provider_error_redacts_icore_key() -> None:
    key = "iba_" + "x" * 32
    error = extraction_providers.sanitize_provider_error(f"Unexpected provider reply for {key}")

    assert key not in error
    assert "[redacted]" in error
