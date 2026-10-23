import httpx

from app.config import Settings


class JeetBotService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def speak(self, text: str, voice_id: str = 'JEE-02', pitch: float = 0.0, speed: float = 1.0) -> dict:
        payload = {'text': text, 'voice_id': voice_id, 'pitch': pitch, 'speed': speed}
        if not self.settings.jeetbot_webhook_url:
            return {'sent': False, 'mode': 'dry-run', 'payload': payload}
        headers = {'Authorization': f'Bearer {self.settings.jeetbot_api_key}'} if self.settings.jeetbot_api_key else {}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.settings.jeetbot_webhook_url, json=payload, headers=headers)
            response.raise_for_status()
        return {'sent': True, 'mode': 'webhook', 'payload': payload}

