from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from docai_core.contracts.domain import AvailableTool, AvailableTools


@dataclass(slots=True)
class CapabilityRegistry:
    available_tools: AvailableTools = dc_field(default_factory=AvailableTools)

    def register_ocr_engine(self, tool: AvailableTool) -> None:
        self.available_tools.available_ocr_engines.append(tool)

    def register_parser(self, tool: AvailableTool) -> None:
        self.available_tools.available_parsers.append(tool)

    def register_model(self, tool: AvailableTool) -> None:
        self.available_tools.available_models.append(tool)

    def register_validator(self, tool: AvailableTool) -> None:
        self.available_tools.available_validators.append(tool)

    def register_recovery_strategy(self, tool: AvailableTool) -> None:
        self.available_tools.available_recovery_strategies.append(tool)

    def snapshot(self) -> AvailableTools:
        return AvailableTools(
            available_ocr_engines=list(self.available_tools.available_ocr_engines),
            available_parsers=list(self.available_tools.available_parsers),
            available_models=list(self.available_tools.available_models),
            available_validators=list(self.available_tools.available_validators),
            available_recovery_strategies=list(self.available_tools.available_recovery_strategies),
        )

    def all_enabled_capabilities(self) -> set[str]:
        capabilities: set[str] = set()
        for tool in self._all_tools():
            if tool.enabled:
                capabilities.update(tool.capabilities)
        return capabilities

    def has_capability(self, capability: str) -> bool:
        return capability in self.all_enabled_capabilities()

    def _all_tools(self) -> list[AvailableTool]:
        return [
            *self.available_tools.available_ocr_engines,
            *self.available_tools.available_parsers,
            *self.available_tools.available_models,
            *self.available_tools.available_validators,
            *self.available_tools.available_recovery_strategies,
        ]
