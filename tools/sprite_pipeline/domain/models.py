"""Small values and structural contracts shared across entry points."""
from dataclasses import dataclass
from typing import Protocol, TypedDict

class ActionConfig(Protocol):
    data: dict
    def action(self, name: str) -> dict: ...

class SliceDescriptor(TypedDict):
    file: str
    source_box: list[int] | tuple[int, int, int, int]

class ActionStep(TypedDict):
    ref: str
    action: str
    frame: int
    duration_ms: int

@dataclass(frozen=True)
class CanvasSpec:
    size: tuple[int, int]
    anchor: dict
