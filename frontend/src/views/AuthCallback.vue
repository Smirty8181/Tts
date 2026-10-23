<script setup>
import { onMounted, ref } from 'vue'
import { CheckCircle2, LoaderCircle, XCircle } from 'lucide-vue-next'
import { fetchTwitchUser, parseOAuthHash } from '../services/twitchAuth'

const status = ref('loading')
const message = ref('Connecting to Twitch...')

onMounted(async () => {
  const { token, state } = parseOAuthHash()
  const storedClientId = localStorage.getItem('stream-sentinel-twitch-client-id') || ''
  const clientId = /^[a-z0-9]{10,}$/i.test(storedClientId) ? storedClientId : (import.meta.env.VITE_TWITCH_CLIENT_ID || 'gragq9yg68pkionhexl3zlgca9rj2p')
  const accountType = state === 'bot' ? 'bot' : 'broadcaster'
  if (!token) { status.value = 'error'; message.value = 'Twitch не вернул OAuth-токен. Повторите вход.'; return }
  try {
    const user = await fetchTwitchUser(token, clientId)
    const prefix = accountType === 'bot' ? 'bot' : 'broadcaster'
    localStorage.setItem(`stream-sentinel-${prefix}-token`, token)
    localStorage.setItem(`stream-sentinel-${prefix}-username`, user.login)
    localStorage.setItem(`stream-sentinel-${prefix}-profile`, JSON.stringify(user))
    if (accountType === 'broadcaster') localStorage.setItem('twitch_channel_name', user.login)
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/auth/twitch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account_type: accountType, token, client_id: clientId, user }) })
    if (!response.ok) throw new Error('Backend could not save Twitch authentication')
    status.value = 'success'; message.value = `Connected as ${user.display_name}`
    window.setTimeout(() => { if (window.opener) window.close(); else window.location.href = '/' }, 900)
  } catch (error) { status.value = 'error'; message.value = error.message }
})
</script>

<template><main class="auth-callback"><div class="auth-card"><LoaderCircle v-if="status === 'loading'" class="spin" :size="30" /><CheckCircle2 v-else-if="status === 'success'" :size="30" class="success-icon" /><XCircle v-else :size="30" class="error-icon" /><h1>{{ status === 'success' ? 'Twitch connected' : status === 'error' ? 'Connection failed' : 'Connecting to Twitch' }}</h1><p>{{ message }}</p></div></main></template>
