import logging

import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)
GEMINI_MODELS_URL = 'https://generativelanguage.googleapis.com/v1beta/models'


class GeminiVerificationError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


async def verify_gemini_api_key(api_key: str) -> dict:
    key = api_key.strip()
    if not key:
        raise GeminiVerificationError('Google Gemini API key is empty', 400)
    try:
        async with httpx.AsyncClient(timeout=15, proxy=get_settings().llm_proxy) as client:
            response = await client.get(GEMINI_MODELS_URL, params={'key': key}, headers={'x-goog-api-key': key})
    except (httpx.TimeoutException, httpx.TransportError) as error:
        raise GeminiVerificationError('Temporary network timeout while verifying the Gemini API key. Please try again.', 504) from error
    try:
        payload = response.json()
    except ValueError:
        payload = {'raw': response.text}
    if response.status_code != 200:
        logger.error('Gemini API verification failed: status=%s payload=%s', response.status_code, payload)
        detail = payload.get('error', {}).get('message') if isinstance(payload, dict) else None
        if response.status_code == 400 and detail and ('location' in detail.lower() or 'region' in detail.lower()):
            detail = 'Геолокация сервера не поддерживается (требуется прокси)'
        elif response.status_code == 403:
            detail = 'Доступ заблокирован (403 Forbidden / Proxy required)'
        elif response.status_code == 401:
            detail = 'Недействительный API-ключ'
        raise GeminiVerificationError(detail or f'Gemini API returned HTTP {response.status_code}', response.status_code)
    models = payload.get('models', []) if isinstance(payload, dict) else []
    logger.info('Gemini API verification succeeded: models=%s', len(models))
    return {'valid': True, 'provider': 'gemini', 'models': len(models)}
