const TWITCH_AUTHORIZE_URL = 'https://id.twitch.tv/oauth2/authorize'
const TWITCH_USER_URL = 'https://api.twitch.tv/helix/users'
const DEFAULT_TWITCH_CLIENT_ID = import.meta.env.VITE_TWITCH_CLIENT_ID || 'gragq9yg68pkionhexl3zlgca9rj2p'

export function buildTwitchAuthUrl({ clientId, accountType = 'broadcaster', redirectUri = `${window.location.origin}/auth/callback`, scopes = ['chat:read', 'chat:edit', 'channel:read:subscriptions', 'user:read:email'] }) {
  const resolvedClientId = (clientId || DEFAULT_TWITCH_CLIENT_ID).trim()
  if (!/^[a-z0-9]{10,}$/i.test(resolvedClientId)) throw new Error('Twitch OAuth Client ID имеет неверный формат')
  const params = new URLSearchParams({ client_id: resolvedClientId, redirect_uri: redirectUri, response_type: 'token', scope: scopes.join(' '), state: accountType })
  return `${TWITCH_AUTHORIZE_URL}?${params.toString()}`
}

export async function fetchTwitchUser(token, clientId = DEFAULT_TWITCH_CLIENT_ID) {
  const response = await fetch(TWITCH_USER_URL, { headers: { Authorization: 'Bearer ' + token, 'Client-ID': clientId } })
  if (!response.ok) throw new Error('Twitch profile request failed')
  const payload = await response.json()
  if (!payload.data?.[0]) throw new Error('Twitch profile not found')
  return payload.data[0]
}

export function parseOAuthHash(hash = window.location.hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  return { token: params.get('access_token') || '', state: params.get('state') || '' }
}
