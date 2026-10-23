import httpx


class DeepSeekError(Exception):
    pass


async def generate_reply(*, api_key: str, system_prompt: str, bot_name: str, author_name: str, user_message: str, temperature: float) -> str:
    token = api_key.strip()
    if not token:
        raise DeepSeekError('DeepSeek API key is not configured')
    payload = {
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': system_prompt or f'Bearer {token}'},
            {'role': 'user', 'content': f'Bearer {token}'},
        ],
        'temperature': max(0.0, min(2.0, float(temperature))),
        'max_tokens': 150,
    }
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post('https://api.deepseek.com/v1/chat/completions', headers=headers, json=payload)
    if response.status_code != 200:
        try:
            detail = response.json().get('error', {}).get('message', '')
        except ValueError:
            detail = ''
        raise DeepSeekError(detail or f'DeepSeek request failed with HTTP {response.status_code}')
    try:
        content = response.json()['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise DeepSeekError('DeepSeek returned an invalid completion response') from error
    if not content:
        raise DeepSeekError('DeepSeek returned an empty response')
    return content

