from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


AgentMessage = Dict[str, Any]


@dataclass(frozen=True)
class AgentContract:
    name: str
    version: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
