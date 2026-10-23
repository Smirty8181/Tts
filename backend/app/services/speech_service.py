from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any


class SpeechService:
    """Lazy local faster-whisper adapter; model loading never blocks the event loop."""

    def __init__(self) -> None:
        self.model: Any = None
        self._load_lock = asyncio.Lock()
        self.model_name = os.getenv('WHISPER_MODEL', 'small')
        self.device = os.getenv('WHISPER_DEVICE', 'cpu')
        self.compute_type = os.getenv('WHISPER_COMPUTE_TYPE', 'int8')

    async def _get_model(self) -> Any:
        if self.model is not None:
            return self.model
        async with self._load_lock:
            if self.model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as error:
                    raise RuntimeError('faster-whisper is not installed') from error
                self.model = await asyncio.to_thread(
                    WhisperModel,
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
        return self.model

    async def transcribe(self, audio: bytes, language: str = 'ru') -> str:
        if not audio:
            return ''
        model = await self._get_model()

        def run() -> str:
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as stream:
                stream.write(audio)
                path = stream.name
            try:
                segments, _ = model.transcribe(
                    path,
                    language=language or None,
                    beam_size=1,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                return ' '.join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass

        return await asyncio.to_thread(run)
