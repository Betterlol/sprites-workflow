"""Small per-project LRU caches. Entries are disposable, never authoritative assets."""

from collections import OrderedDict
from typing import Generic, TypeVar

Value = TypeVar("Value")


class RenderCache(Generic[Value]):
    def __init__(self, limit: int = 64 * 1024 * 1024) -> None:
        self.limit = limit
        self.bytes = 0
        self.entries: OrderedDict[str, tuple[Value, int]] = OrderedDict()

    def get(self, key: str) -> Value | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        self.entries.move_to_end(key)
        return entry[0]

    def put(self, key: str, value: Value, size: int) -> None:
        previous = self.entries.pop(key, None)
        if previous is not None:
            self.bytes -= previous[1]
        if size > self.limit:
            return
        self.entries[key] = (value, size)
        self.bytes += size
        while self.bytes > self.limit:
            _, (_, removed) = self.entries.popitem(last=False)
            self.bytes -= removed
