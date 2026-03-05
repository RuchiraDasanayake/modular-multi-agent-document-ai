"""Agent contract definitions for typed inter-agent communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AgentMessage = dict[str, Any]

@dataclass(frozen=True)
class AgentContract:
    name: str
    version: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
