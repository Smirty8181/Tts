from dataclasses import asdict, dataclass
from threading import Lock


@dataclass
class MoodState:
    hype: int = 78
    sarcasm: int = 42
    empathy: int = 64
    label: str = 'hyped'


class MoodService:
    def __init__(self) -> None:
        self._state = MoodState()
        self._lock = Lock()

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._state)

    def apply_event(self, event: str) -> dict:
        values = {
            'died': MoodState(25, 68, 88, 'sympathetic'),
            'victory': MoodState(98, 34, 52, 'hyped'),
            'silence': MoodState(12, 55, 44, 'chilling'),
        }
        with self._lock:
            self._state = values.get(event, self._state)
            return asdict(self._state)

    def update_from_signals(self, chat_velocity: int, audio_energy: float) -> dict:
        with self._lock:
            self._state.hype = max(0, min(100, round(self._state.hype + chat_velocity * 2 + audio_energy * 5 - 8)))
            self._state.label = 'hyped' if self._state.hype > 70 else 'chilling' if self._state.hype < 30 else self._state.label
            return asdict(self._state)
