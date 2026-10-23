import httpx


class TwitchVerificationError(Exception):
    pass


async def fetch_stream_status(username: str, client_id: str, token: str) -> bool:
    access_token = token.strip().removeprefix('oauth:').strip()
    headers = {'Client-ID': client_id.strip(), 'Authorization': f'Bearer {access_token}'}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get('https://api.twitch.tv/helix/streams', headers=headers, params={'user_login': username.strip()})
        if response.status_code != 200:
            return False
        return bool(response.json().get('data'))


async def verify_twitch_credentials(username: str, client_id: str, token: str) -> dict:
    username = username.strip()
    client_id = client_id.strip()
    access_token = token.strip().removeprefix('oauth:').strip()
    if not username:
        raise TwitchVerificationError('Twitch username is required')
    if not client_id or not client_id.isalnum():
        raise TwitchVerificationError('Twitch Client ID is missing or invalid')
    if not access_token:
        raise TwitchVerificationError('Twitch OAuth token is missing')
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get('https://id.twitch.tv/oauth2/validate', headers={'Authorization': headers['Authorization']})
        if response.status_code != 200:
            detail = response.json().get('message', '') if response.headers.get('content-type', '').startswith('application/json') else ''
            raise TwitchVerificationError(detail or f'Twitch token validation failed ({response.status_code})')
        token_data = response.json()
        token_client_id = token_data.get('client_id', '')
        headers['Client-ID'] = token_client_id or client_id
        user_response = await client.get('https://api.twitch.tv/helix/users', headers=headers, params={'login': username})
        if user_response.status_code != 200 or not user_response.json().get('data'):
            detail = user_response.json().get('message', '') if user_response.headers.get('content-type', '').startswith('application/json') else ''
            raise TwitchVerificationError(detail or f'Twitch user lookup failed ({user_response.status_code})')
        user = user_response.json()['data'][0]
        token_user_id = token_data.get('user_id')
        if token_user_id and token_user_id != user['id']:
            raise TwitchVerificationError(f'This token belongs to Twitch account {token_user_id}, not @{username}. Use a token generated while logged into @{username}.')
        return {'valid': True, 'username': user['login'], 'display_name': user['display_name'], 'user_id': user['id'], 'scopes': token_data.get('scopes', []), 'token_client_id': token_client_id or client_id}

