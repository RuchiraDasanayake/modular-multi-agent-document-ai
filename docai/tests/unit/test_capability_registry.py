from docai_core.capabilities.registry import CapabilityRegistry
from docai_core.contracts.domain import AvailableTool, AvailableTools


def test_can_register_ocr_engine() -> None:
    registry = CapabilityRegistry()
    tool = AvailableTool(
        tool_id="ocr-1",
        tool_type="ocr",
        capabilities=["text_output"],
        enabled=True,
    )

    registry.register_ocr_engine(tool)

    assert len(registry.available_tools.available_ocr_engines) == 1
    assert registry.available_tools.available_ocr_engines[0].tool_id == "ocr-1"


def test_can_register_model() -> None:
    registry = CapabilityRegistry()
    tool = AvailableTool(
        tool_id="model-1",
        tool_type="model",
        capabilities=["json_output"],
        enabled=True,
    )

    registry.register_model(tool)

    assert len(registry.available_tools.available_models) == 1
    assert registry.available_tools.available_models[0].tool_id == "model-1"


def test_snapshot_returns_available_tools() -> None:
    registry = CapabilityRegistry()
    registry.register_parser(
        AvailableTool(
            tool_id="parser-1",
            tool_type="parser",
            capabilities=["table_detection"],
            enabled=True,
        )
    )

    snapshot = registry.snapshot()

    assert isinstance(snapshot, AvailableTools)
    assert len(snapshot.available_parsers) == 1
    assert snapshot.available_parsers[0].tool_id == "parser-1"


def test_enabled_capabilities_are_collected() -> None:
    registry = CapabilityRegistry()
    registry.register_ocr_engine(
        AvailableTool(
            tool_id="ocr-1",
            tool_type="ocr",
            capabilities=["text_output", "bbox_output"],
            enabled=True,
        )
    )
    registry.register_model(
        AvailableTool(
            tool_id="model-1",
            tool_type="model",
            capabilities=["json_output"],
            enabled=True,
        )
    )

    capabilities = registry.all_enabled_capabilities()

    assert "text_output" in capabilities
    assert "bbox_output" in capabilities
    assert "json_output" in capabilities


def test_disabled_tools_do_not_contribute_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.register_ocr_engine(
        AvailableTool(
            tool_id="ocr-disabled",
            tool_type="ocr",
            capabilities=["text_output"],
            enabled=False,
        )
    )

    capabilities = registry.all_enabled_capabilities()

    assert "text_output" not in capabilities


def test_has_capability_true_for_enabled_capability() -> None:
    registry = CapabilityRegistry()
    registry.register_model(
        AvailableTool(
            tool_id="model-1",
            tool_type="model",
            capabilities=["json_output"],
            enabled=True,
        )
    )

    assert registry.has_capability("json_output") is True


def test_has_capability_false_for_missing_capability() -> None:
    registry = CapabilityRegistry()
    registry.register_validator(
        AvailableTool(
            tool_id="validator-1",
            tool_type="validator",
            capabilities=["required_field_check"],
            enabled=True,
        )
    )

    assert registry.has_capability("table_detection") is False


def test_has_capability_false_if_capability_only_on_disabled_tool() -> None:
    registry = CapabilityRegistry()
    registry.register_parser(
        AvailableTool(
            tool_id="parser-disabled",
            tool_type="parser",
            capabilities=["table_detection"],
            enabled=False,
        )
    )

    assert registry.has_capability("table_detection") is False
