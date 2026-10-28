"""Small per-project LRU caches. Entries are disposable, never authoritative assets."""
from collections import OrderedDict


class RenderCache:
    def __init__(self, limit=64 * 1024 * 1024):
        self.limit = limit
        self.bytes = 0
        self.entries = OrderedDict()

    def get(self, key):
        entry = self.entries.get(key)
        if entry is None:
            return None
        self.entries.move_to_end(key)
        return entry[0]

    def put(self, key, value, size):
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
