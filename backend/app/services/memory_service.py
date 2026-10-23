from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock


@dataclass
class MemoryItem:
    id: int
    type: str
    value: str


class MemoryService:
    def __init__(self) -> None:
        self._short_term: deque[str] = deque(maxlen=20)
        self._long_term = [
            MemoryItem(1, 'LORE', 'Streamer always blames the chair after a misplay.'),
            MemoryItem(2, 'MEME', 'The 1 HP clutch is now called the Lazarus.'),
        ]
        self._next_id = 3
        self._lock = Lock()

    def snapshot(self) -> dict:
        with self._lock:
            return {'short_term': list(self._short_term), 'long_term': [asdict(item) for item in self._long_term]}

    def add(self, item_type: str, value: str) -> dict:
        with self._lock:
            item = MemoryItem(self._next_id, item_type.upper(), value.strip())
            self._next_id += 1
            self._long_term.append(item)
            return asdict(item)

    def delete(self, item_id: int) -> bool:
        with self._lock:
            before = len(self._long_term)
            self._long_term = [item for item in self._long_term if item.id != item_id]
            return len(self._long_term) != before

    def reset(self) -> None:
        with self._lock:
            self._short_term.clear()
            self._long_term.clear()
