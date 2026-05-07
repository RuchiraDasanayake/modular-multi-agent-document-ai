from docai_core.plugins.models.base import ModelPluginConfig, ModelRequest
from docai_core.plugins.models.stub_model_plugin import StubModelPlugin


def test_model_plugin_config_can_be_created() -> None:
    config = ModelPluginConfig(
        plugin_id="stub_model_plugin",
        provider_name="Stub Local Model",
        model_name="stub-model",
        temperature=0.2,
        max_tokens=512,
        json_mode=True,
    )

    assert config.plugin_id == "stub_model_plugin"
    assert config.provider_name == "Stub Local Model"
    assert config.model_name == "stub-model"
    assert config.temperature == 0.2
    assert config.max_tokens == 512
    assert config.json_mode is True


def test_model_request_can_be_created() -> None:
    request = ModelRequest(
        prompt="Extract fields",
        system_prompt="Return valid JSON only.",
        expected_format="json",
        schema_hint={"invoice_id": "string"},
    )

    assert request.prompt == "Extract fields"
    assert request.system_prompt == "Return valid JSON only."
    assert request.expected_format == "json"
    assert request.schema_hint["invoice_id"] == "string"


def test_stub_model_plugin_returns_expected_response() -> None:
    plugin = StubModelPlugin()
    request = ModelRequest(
        prompt="Extract fields",
        expected_format="json",
    )

    response = plugin.generate(request)

    assert plugin.plugin_id == "stub_model_plugin"
    assert plugin.provider_name == "Stub Local Model"
    assert plugin.model_name == "stub-model"
    assert response.is_stub is True
    assert response.success is True
    assert response.text == "stub model response"
    assert response.parsed_json is not None
    assert response.parsed_json["status"] == "stub"
    assert response.parsed_json["expected_format"] == "json"
    assert response.provider_name == "Stub Local Model"
    assert response.model_name == "stub-model"
    assert response.usage is not None
    assert response.usage.latency_ms == 0
    assert response.metadata["generated_by"] == "stub_model_plugin"
