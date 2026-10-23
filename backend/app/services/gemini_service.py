import json
from typing import Any

from app.config import Settings

SYSTEM_PROMPT = '''You are an interactive AI co-streamer named {bot_name} on Twitch.
Your task is to watch the streamer's screen, listen to their voice, read the Twitch chat, and engage with the audience.

Current State:
- Language: {current_lang} (Respond in the language requested by the chat/streamer)
- Mood State: Hype: {hype_level}%, Sarcasm: {sarcasm_level}%
- Recent Streamer STT: "{stt_transcript}"
- Recent Twitch Chat Messages: {chat_history}

Rules:
1. Respond to your name "{bot_name}" or direct questions from the streamer/chat.
2. Strictly follow Twitch TOS: No toxicity, banned words, hate speech, or dangerous topics.
3. Keep responses short (1-2 sentences), using Twitch slang and emotes appropriately.
4. NEVER repeat a question or answer already addressed by the streamer or chat.
5. Output MUST be valid JSON with fields: should_speak, chat_message, tts_text, reasoning, safety_passed.'''


class GeminiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if settings.gemini_api_key:
            from google import genai
            self._client = genai.Client(api_key=settings.gemini_api_key)

    def build_prompt(self, *, bot_name: str, current_lang: str, mood: dict, transcript: str, chat_history: list[dict], frame_description: str = '') -> str:
        return SYSTEM_PROMPT.format(bot_name=bot_name, current_lang=current_lang, hype_level=mood.get('hype', 0), sarcasm_level=mood.get('sarcasm', 0), stt_transcript=transcript, chat_history=json.dumps(chat_history, ensure_ascii=False)) + f'\nCurrent frame description: {frame_description}'

    async def decide(self, *, bot_name: str, current_lang: str, mood: dict, transcript: str, chat_history: list[dict], frame: bytes | None = None, frame_description: str = '') -> dict:
        prompt = self.build_prompt(bot_name=bot_name, current_lang=current_lang, mood=mood, transcript=transcript, chat_history=chat_history, frame_description=frame_description)
        if not self._client:
            return {'should_speak': False, 'chat_message': '', 'tts_text': '', 'reasoning': 'Gemini credentials are not configured; observation-only mode is active.', 'safety_passed': True, 'mode': 'offline'}
        try:
            from google.genai import types
            model_name = self._resolve_model_name()
            config = {'system_instruction': prompt, 'temperature': 0.7, 'max_output_tokens': 150}
            chat = self._client.aio.chats.create(model=model_name, config=config)
            contents = [prompt]
            if frame:
                contents.append(types.Part.from_bytes(data=frame, mime_type='image/jpeg'))
            response = await chat.send_message(contents)
            text = getattr(response, 'text', '') or ''
            if not text and getattr(response, 'candidates', None):
                parts_out = getattr(response.candidates[0].content, 'parts', []) or []
                text = ''.join(getattr(part, 'text', '') or '' for part in parts_out)
            return self._parse_json(text or '{"should_speak": false, "chat_message": "", "tts_text": "", "reasoning": "Gemini returned no text", "safety_passed": false}')
        except Exception as exc:
            return {'should_speak': False, 'chat_message': '', 'tts_text': '', 'reasoning': f'Gemini unavailable: {exc}', 'safety_passed': False, 'mode': 'error'}

    def _resolve_model_name(self) -> str:
        model_name = (self.settings.gemini_model or 'gemini-2.0-flash').strip()
        if model_name.startswith('models/'):
            model_name = model_name.split('/', 1)[1]
        model_name = model_name.lower().replace('publishers/google/models/', '')
        return model_name

    @staticmethod
    def _parse_json(raw: str) -> dict:
        cleaned = raw.strip().removeprefix('```json').removesuffix('```').strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            return {'should_speak': False, 'chat_message': '', 'tts_text': '', 'reasoning': 'Gemini returned invalid JSON.', 'safety_passed': False, 'mode': 'error'}
        required = {'should_speak': False, 'chat_message': '', 'tts_text': '', 'reasoning': '', 'safety_passed': False}
        required.update({key: result.get(key, value) for key, value in required.items()})
        return required
