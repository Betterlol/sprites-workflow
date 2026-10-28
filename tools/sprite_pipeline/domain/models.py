"""Small values and structural contracts shared across entry points."""

from dataclasses import dataclass
from typing import Callable, Protocol, TypedDict, TypeVar

Value = TypeVar("Value")
Progress = Callable[[int, int, str], None]


class Cache(Protocol[Value]):
    def get(self, key: str) -> Value | None: ...
    def put(self, key: str, value: Value, size: int) -> None: ...


class Cancellation(Protocol):
    def is_set(self) -> bool: ...


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


class ReviewStep(ActionStep):
    clip: int
    repetition: int
    boundary: bool


@dataclass(frozen=True)
class CanvasSpec:
    size: tuple[int, int]
    anchor: dict
