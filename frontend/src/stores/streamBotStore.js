import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import i18n from '../i18n'
import { buildTwitchAuthUrl } from '../services/twitchAuth'

const seedChat = []

export const useStreamBotStore = defineStore('streamBot', () => {
  const language = ref(localStorage.getItem('stream-sentinel-language') || i18n.global.locale.value || 'en')
  const activeNav = ref('overview')
  const isLive = ref(false)
  const autoReply = ref(false)
  const tosGuard = ref(false)
  const autoScroll = ref(true)
  const preModeration = ref(true)
  const chat = ref(seedChat)
  const logs = ref([])
  const queue = ref([])
  const mood = ref({ hype: 0, sarcasm: 0, empathy: 0, label: 'unknown' })
  const memories = ref([])
  const memoryQuery = ref('')
  const memoryProfile = ref('all')
  const memoryProfiles = ref(JSON.parse(localStorage.getItem('stream-sentinel-memory-profiles') || '[{"id":"all","name":"Р’СЃРµ Р·Р°РјРµС‚РєРё"},{"id":"lore","name":"Р›РѕСЂ"},{"id":"meme","name":"РњРµРјС‹"}]'))
  const conversationMode = ref(localStorage.getItem('stream-sentinel-conversation-mode') || 'balanced')
  const llmObservability = ref([])
  const transcript = ref('')
  const lastFrame = ref('')
  const frameConfidence = ref(0)
  const backendConnected = ref(false)
  const websocketState = ref('offline')
  const accountMenuOpen = ref(false)
  const broadcasterToken = ref(localStorage.getItem('stream-sentinel-broadcaster-token') || '')
  const botToken = ref(localStorage.getItem('stream-sentinel-bot-token') || '')
  const broadcasterUsername = ref(localStorage.getItem('stream-sentinel-broadcaster-username') || '')
  const defaultClientId = import.meta.env.VITE_TWITCH_CLIENT_ID || 'gragq9yg68pkionhexl3zlgca9rj2p'
  const legacyClientId = 'gp762nuuoqcoxypju8c569th9wz7q5'
  const storedClientId = localStorage.getItem('stream-sentinel-twitch-client-id')
  const storedBroadcasterClientId = [localStorage.getItem('stream-sentinel-broadcaster-client-id'), storedClientId].find(value => value && value !== legacyClientId) || defaultClientId
  const storedBotClientId = [localStorage.getItem('stream-sentinel-bot-client-id'), storedClientId].find(value => value && value !== legacyClientId) || defaultClientId
  const broadcasterClientId = ref(storedBroadcasterClientId)
  const botUsername = ref(localStorage.getItem('stream-sentinel-bot-username') || '')
  const botClientId = ref(storedBotClientId)
  const accountVerification = ref({ broadcaster: '', bot: '', broadcasterError: false, botError: false })
  const authNotice = ref('')
  const settings = ref({ bot_name: 'Sentinel', system_prompt: 'Be sharp, observant, and concise. React only when you add energy.', response_triggers: ['Р—РµС‚РєР°', 'Р—РµС‚РѕС‡РєР°', 'РќРµР№СЂРѕР—РµС‚РєР°', 'neyrozetka', 'Р—РµС‚'], temperature: 0.68, cooldown: 3.5, attention_threshold: 72, jeetbot_endpoint: '', voice_id: 'JEE-02', speed: 1.05, pitch: 0, tos_guard: true, auto_reply: true, llm_provider: 'gemini', gemini_api_key: '', deepseek_api_key: '', openai_api_key: '', groq_api_key: '', elevenlabs_api_key: '', groq_model: 'openai/gpt-oss-20b', elevenlabs_voice_id: '', tts_provider: 'jeetbot', youtube_channel: '', youtube_token: '', twitch_broadcaster_token: '', twitch_bot_token: '', obs_url: 'ws://127.0.0.1:4455', obs_password: '', obs_enabled: false, obs_capture_interval: 5, avatar_idle: '', avatar_talking: '', avatar_rage: '', avatar_hype: '' })
  const defaultBotName = localStorage.getItem('stream-sentinel-bot-name') || ''
  const botNameCustom = ref(localStorage.getItem('stream-sentinel-bot-name-custom') === 'true')
  if (defaultBotName) settings.value.bot_name = defaultBotName
  const overlayEvent = ref(null)
  const channel = ref({ login: '', displayName: '', avatar: '', live: false, botUser: '' })
  const sandboxMode = ref(localStorage.getItem('stream-sentinel-sandbox') !== 'false')
  const sandboxInput = ref('!askbot РџСЂРёРІРµС‚, Sentinel!')
  const providerStatus = ref({})
  const systemNotice = ref('')
  const notifications = ref([])
  const sttListening = ref(false)
  const visionDescription = ref('')
  let recognition
  const muted = ref(false)
  const streamStatus = ref({ obs: false, twitch: false })
  let socket
  let reconnectTimer
  let heartbeatTimer
  let heartbeatTimeout
  let backendHealthTimer
  const frameDescription = computed(() => visionDescription.value || '')
  const filteredMemories = computed(() => memories.value.filter(item => {
    const query = memoryQuery.value.trim().toLowerCase()
    return (!query || `${item.type} ${item.value}`.toLowerCase().includes(query)) &&
      (memoryProfile.value === 'all' || item.type?.toLowerCase() === memoryProfile.value)
  }))

  function setLanguage(value) {
    language.value = value
    i18n.global.locale.value = value
    localStorage.setItem('stream-sentinel-language', value)
  }

  async function refreshLlmObservability() {
    try {
      const result = await api('/api/observability/llm')
      llmObservability.value = Array.isArray(result?.items) ? result.items : []
    } catch {
      llmObservability.value = []
    }
  }

  async function loadPersistedState() {
    try {
      const storedSettings = JSON.parse(localStorage.getItem('stream-sentinel-settings') || '{}')
      if (storedSettings && typeof storedSettings === 'object') {
        settings.value = { ...settings.value, ...storedSettings }
      }
      const persisted = await api('/api/settings')
      if (persisted && typeof persisted === 'object') {
        settings.value = { ...settings.value, ...persisted }
        broadcasterUsername.value = persisted.twitch_channel || broadcasterUsername.value
        botUsername.value = persisted.twitch_bot_username || botUsername.value
        broadcasterClientId.value = persisted.twitch_broadcaster_client_id || broadcasterClientId.value
        botClientId.value = persisted.twitch_bot_client_id || botClientId.value
        localStorage.setItem('stream-sentinel-settings', JSON.stringify(settings.value))
      }
      const state = await api('/api/state')
      if (state?.settings) {
        settings.value = { ...settings.value, ...state.settings }
        autoReply.value = settings.value.auto_reply !== false
        tosGuard.value = settings.value.tos_guard !== false
        preModeration.value = !autoReply.value
        localStorage.setItem('stream-sentinel-settings', JSON.stringify(settings.value))
      }
      if (state?.twitch) {
        channel.value = {
          login: state.twitch.channel || channel.value.login || '',
          displayName: state.twitch.display_name || channel.value.displayName || '',
          avatar: state.twitch.profile_image_url || channel.value.avatar || '',
          live: Boolean(state.twitch.live),
          botUser: state.twitch.bot_user || channel.value.botUser || ''
        }
      }
      if (state?.accounts) {
        const broadcaster = state.accounts.find(account => account.account_type === 'broadcaster')
        const bot = state.accounts.find(account => account.account_type === 'bot')
        if (broadcaster) {
          broadcasterUsername.value = broadcaster.username || broadcasterUsername.value
          broadcasterClientId.value = broadcaster.client_id || broadcasterClientId.value
        }
        if (bot) {
          botUsername.value = bot.username || botUsername.value
          botClientId.value = bot.client_id || botClientId.value
        }
      }
      if (language.value) {
        localStorage.setItem('stream-sentinel-language', language.value)
      }
    } catch (error) {
      systemNotice.value = language.value === 'ru'
        ? 'РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃРѕСЃС‚РѕСЏРЅРёРµ СЃРµСЂРІРµСЂР°'
        : 'Could not load server state'
    }
  }
  function setNav(value) { activeNav.value = value }
  function setConversationMode(value) { conversationMode.value = value; localStorage.setItem('stream-sentinel-conversation-mode', value) }
  function addMemoryProfile(name) {
    const normalized = name.trim()
    if (!normalized) return
    const id = normalized.toLowerCase().replace(/[^a-z0-9Р°-СЏС‘]+/gi, '-')
    if (!memoryProfiles.value.some(profile => profile.id === id)) {
      memoryProfiles.value.push({ id, name: normalized })
      localStorage.setItem('stream-sentinel-memory-profiles', JSON.stringify(memoryProfiles.value))
    }
    memoryProfile.value = id
  }
  function toggleAccountMenu() { accountMenuOpen.value = !accountMenuOpen.value }
  function openTwitchAuth(accountType = 'broadcaster') {
    const configuredClientId = accountType === 'broadcaster' ? broadcasterClientId.value : botClientId.value
    const clientId = /^[a-z0-9]{10,}$/i.test(configuredClientId || '') ? configuredClientId : (import.meta.env.VITE_TWITCH_CLIENT_ID || 'gragq9yg68pkionhexl3zlgca9rj2p')
    try {
      authNotice.value = ''
      localStorage.setItem('stream-sentinel-twitch-client-id', clientId)
      window.open(buildTwitchAuthUrl({ clientId, accountType }), 'twitch-auth', 'width=620,height=760')
    } catch (error) { authNotice.value = error.message }
  }
  async function saveAccountTokens() {
    localStorage.setItem('stream-sentinel-broadcaster-token', broadcasterToken.value)
    localStorage.setItem('stream-sentinel-bot-token', botToken.value)
    localStorage.setItem('stream-sentinel-broadcaster-username', broadcasterUsername.value)
    localStorage.setItem('stream-sentinel-broadcaster-client-id', broadcasterClientId.value)
    localStorage.setItem('stream-sentinel-twitch-client-id', broadcasterClientId.value)
    localStorage.setItem('stream-sentinel-bot-username', botUsername.value)
    localStorage.setItem('stream-sentinel-bot-client-id', botClientId.value)
    localStorage.setItem('stream-sentinel-twitch-bot-client-id', botClientId.value)
    const payload = {
      twitch_channel: broadcasterUsername.value,
      twitch_bot_username: botUsername.value,
      twitch_broadcaster_client_id: broadcasterClientId.value,
      twitch_bot_client_id: botClientId.value,
      ...(broadcasterToken.value ? { twitch_broadcaster_token: broadcasterToken.value } : {}),
      ...(botToken.value ? { twitch_bot_token: botToken.value } : {})
    }
    try {
      await api('/api/settings', { method: 'PUT', body: JSON.stringify(payload) })
      systemNotice.value = language.value === 'ru' ? 'Р”Р°РЅРЅС‹Рµ Twitch СЃРѕС…СЂР°РЅРµРЅС‹ РІ Р‘Р”' : 'Twitch data saved to database'
    } catch (error) {
      systemNotice.value = language.value === 'ru' ? `РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ Twitch: ${error.message}` : `Could not save Twitch: ${error.message}`
      return false
    }
    accountMenuOpen.value = false
    return true
  }
  function syncBotNameFromAccount() {
    if (!botNameCustom.value) settings.value.bot_name = botUsername.value
  }
  function setCustomBotName(value) {
    settings.value.bot_name = value
    botNameCustom.value = true
    localStorage.setItem('stream-sentinel-bot-name-custom', 'true')
  }
  async function api(path, options = {}) {
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
    if (!response.ok) throw new Error(await response.text())
    return response.json()
  }
  async function verifyAccount(accountType) {
    const prefix = accountType === 'broadcaster' ? 'broadcaster' : 'bot'
    try {
      const result = await api('/api/twitch/verify', { method: 'POST', body: JSON.stringify({ account_type: accountType, username: accountType === 'broadcaster' ? broadcasterUsername.value : botUsername.value, ...(accountType === 'broadcaster' && broadcasterClientId.value ? { client_id: broadcasterClientId.value } : {}), token: accountType === 'broadcaster' ? broadcasterToken.value : botToken.value }) })
      accountVerification.value[prefix] = `вњ“ ${result.username}`
      accountVerification.value[`${prefix}Error`] = false
      await saveAccountTokens()
      if (accountType === 'bot') {
        const channelName = broadcasterUsername.value || localStorage.getItem('twitch_channel_name') || ''
        if (channelName) {
          try {
            const irc = await api('/api/twitch/irc/connect', { method: 'POST', body: JSON.stringify({ channel: channelName, bot_username: botUsername.value, bot_token: botToken.value }) })
            appendLog('action', 'ircConnected')
            syncBotNameFromAccount()
            localStorage.setItem('stream-sentinel-bot-name', botUsername.value)
            streamStatus.value.twitch = Boolean(irc.connected)
          } catch { appendLog('safety', 'ircFailed') }
        }
      }
    } catch (error) {
      const offline = error instanceof TypeError || String(error.message).toLowerCase().includes('failed to fetch')
      let backendMessage = ''
      if (!offline) {
        try { backendMessage = JSON.parse(error.message).detail || '' } catch { backendMessage = '' }
      }
      accountVerification.value[prefix] = offline ? i18n.global.t('account.backendOffline') : backendMessage || i18n.global.t('account.verifyFailed')
      accountVerification.value[`${prefix}Error`] = true
      await saveAccountTokens()
    }
  }
  async function saveSettings(payload = settings.value) {
    const nextSettings = { ...settings.value, ...payload }
    settings.value = nextSettings
    localStorage.setItem('stream-sentinel-settings', JSON.stringify(nextSettings))
    try {
      const persisted = await api('/api/settings', { method: 'PUT', body: JSON.stringify(nextSettings) })
      settings.value = { ...nextSettings, ...(persisted || {}) }
      localStorage.setItem('stream-sentinel-settings', JSON.stringify(settings.value))
      systemNotice.value = language.value === 'ru' ? 'РќР°СЃС‚СЂРѕР№РєРё СЃРѕС…СЂР°РЅРµРЅС‹' : 'Settings saved'
    } catch (error) {
      systemNotice.value = language.value === 'ru'
        ? `РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ РЅР°СЃС‚СЂРѕР№РєРё: ${error.message}`
        : `Settings were not saved: ${error.message}`
      return null
    }
    return settings.value
  }
  async function setLlmProvider(provider) {
    const allowed = ['gemini', 'groq', 'deepseek', 'openai']
    if (!allowed.includes(provider)) return
    const previous = settings.value.llm_provider
    settings.value.llm_provider = provider
    try {
      const saved = await saveSettings({ llm_provider: provider })
      if (!saved) {
        settings.value.llm_provider = previous
        return
      }
      providerStatus.value[provider] = providerStatus.value[provider] || ''
    } catch {
      settings.value.llm_provider = previous
    }
  }
  async function setRuntimeToggle(name, value) {
    const previous = settings.value[name]
    if (name === 'tos_guard') tosGuard.value = value
    if (name === 'auto_reply') autoReply.value = value
    settings.value[name] = value
    const saved = await saveSettings({ [name]: value })
    if (!saved) {
      settings.value[name] = previous
      if (name === 'tos_guard') tosGuard.value = previous
      if (name === 'auto_reply') autoReply.value = previous
    }
  }
  function simulateEvent(type) {
    if (type === 'died') mood.value = { hype: 25, sarcasm: 68, empathy: 88, label: 'sympathetic' }
    if (type === 'victory') mood.value = { hype: 98, sarcasm: 34, empathy: 52, label: 'hyped' }
    if (type === 'silence') mood.value = { hype: 12, sarcasm: 55, empathy: 44, label: 'chilling' }
    logs.value.unshift({ id: Date.now(), type: 'reasoning', icon: 'вњ¦', textKey: type === 'died' ? 'heard' : 'saw', time: 'now' })
  }
  function appendLog(type, textKey) { logs.value.unshift({ id: Date.now(), type, icon: 'в†—', textKey, time: 'now' }) }
  async function approveQueue(id) {
    try { await api(`/api/queue/${id}/approve`, { method: 'POST' }); appendLog('action', 'approved'); removeQueue(id) } catch { appendLog('safety', 'rejected') }
}
  async function editQueue(item) { item.response = `${item.response} рџ”Ґ`; appendLog('reasoning', 'edited'); try { await api(`/api/queue/${item.id}/approve`, { method: 'POST', body: JSON.stringify({ response: item.response }) }) } catch { /* offline edit remains local */ } }
  async function rejectQueue(id) { try { await api(`/api/queue/${id}/reject`, { method: 'POST' }); appendLog('safety', 'rejected'); removeQueue(id) } catch { appendLog('safety', 'rejected') } }
  async function sendQueueToJeet(id) { try { await api(`/api/queue/${id}/jeetbot`, { method: 'POST' }); appendLog('action', 'action'); removeQueue(id) } catch { appendLog('safety', 'rejected') } }
  function removeQueue(id) { queue.value = queue.value.filter(item => item.id !== id) }
  async function addMemory() { const value = language.value === 'ru' ? 'РќРѕРІР°СЏ Р·Р°РјРµС‚РєР° РёР· С‚РµРєСѓС‰РµРіРѕ СЌС„РёСЂР°.' : 'New note from the current stream.'; const item = await api('/api/memory', { method: 'POST', body: JSON.stringify({ type: 'NOTE', value }) }); memories.value.push(item) }
  async function removeMemory(id) { try { await api(`/api/memory/${id}`, { method: 'DELETE' }) } finally { memories.value = memories.value.filter(item => item.id !== id) } }
  async function resetMemory() { try { await api('/api/memory/reset', { method: 'POST' }) } finally { memories.value = [] } }
  function addChatMessage() {}
  function applyBackendMessage(message) {
    if (message.type === 'state') {
      backendConnected.value = true
      streamStatus.value = { ...streamStatus.value, twitch: Boolean(message.twitch?.connected) }
      if (message.mood) mood.value = message.mood
      if (message.memory?.long_term) memories.value = message.memory.long_term
      if (message.queue) queue.value = message.queue
      if (message.settings) {
        settings.value = { ...settings.value, ...message.settings }
        autoReply.value = settings.value.auto_reply !== false
        preModeration.value = !autoReply.value
      }
      if (message.twitch) channel.value = { login: message.twitch.channel || '', displayName: message.twitch.display_name || '', avatar: message.twitch.profile_image_url || '', live: Boolean(message.twitch.live), botUser: message.twitch.bot_user || '' }
    }
    if (message.type === 'mood' && message.mood) mood.value = message.mood
    if (message.type === 'memory' && message.memory?.long_term) memories.value = message.memory.long_term
    if (message.type === 'CHAT_MESSAGE_RECEIVED' && message.message && message.message.badge !== 'TEST') {
      chat.value.push({ id: Date.now(), ...message.message, time: 'now' })
      if (chat.value.length > 150) chat.value.splice(0, chat.value.length - 150)
    }
    if (message.type === 'IRC_STATUS') {
      streamStatus.value.twitch = Boolean(message.connected)
      if (!message.connected) systemNotice.value = message.message || 'Twitch IRC РѕС‚РєР»СЋС‡С‘РЅ'
    }
    if (message.type === 'OBS_STATUS') streamStatus.value.obs = Boolean(message.connected)
    if (['BOT_START_TALKING', 'BOT_STOP_TALKING', 'AVATAR_UPDATED'].includes(message.type)) overlayEvent.value = message
    if (message.type === 'STREAMER_ANSWER') overlayEvent.value = { type: 'BOT_START_TALKING', text: message.text, avatar_state: 'talking' }
    if (message.type === 'TRIGGER_MEME_FX') overlayEvent.value = message
    if (message.type === 'VIEWER_COMMAND_ANSWER') {
      queue.value.unshift(message.item)
      if (queue.value.length > 50) queue.value.length = 50
      appendLog('action', 'action')
    }
    if (message.type === 'SYSTEM_ERROR') { systemNotice.value = message.message || 'РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё РІ Twitch'; appendLog('safety', 'ircFailed') }
    if (message.type === 'NOTIFICATION') {
      notifications.value.unshift({ id: Date.now(), level: message.level || 'info', message: message.message })
      notifications.value = notifications.value.slice(0, 30)
      systemNotice.value = message.message || ''
    }
    if (message.type === 'MOOD_STATE_CHANGED' && message.mood) mood.value = message.mood
    if (message.type === 'telemetry') {
      transcript.value = message.transcript || transcript.value
      lastFrame.value = message.last_frame || lastFrame.value
      frameConfidence.value = message.confidence || frameConfidence.value
    }
    if (message.type === 'STT_TRANSCRIPT') transcript.value = message.transcript
    if (message.type === 'VISION_FRAME_ANALYZED') { visionDescription.value = message.description; frameConfidence.value = message.confidence || frameConfidence.value }
  }
  function stopHeartbeat() {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (heartbeatTimeout) {
      window.clearTimeout(heartbeatTimeout)
      heartbeatTimeout = null
    }
  }
  function startHeartbeat() {
    stopHeartbeat()
    heartbeatTimer = window.setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'PING' }))
        if (heartbeatTimeout) window.clearTimeout(heartbeatTimeout)
        heartbeatTimeout = window.setTimeout(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.close()
        }, 10000)
      }
    }, 25000)
  }
  function connectSocket() {
    if (typeof window === 'undefined' || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    websocketState.value = 'connecting'
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = import.meta.env.VITE_BACKEND_URL || `${protocol}://${window.location.hostname}:8000`
    socket = new WebSocket(`${host.replace(/^http/, 'ws')}/ws`)
    socket.onopen = () => { backendConnected.value = true; websocketState.value = 'online'; startHeartbeat() }
    socket.onmessage = (event) => {
      let message
      try {
        message = JSON.parse(event.data)
      } catch {
        return
      }
      if (message.type === 'PING') {
        socket.send(JSON.stringify({ type: 'PONG' }))
        return
      }
      if (message.type === 'PONG') {
        if (heartbeatTimeout) {
          window.clearTimeout(heartbeatTimeout)
          heartbeatTimeout = null
        }
        return
      }
      applyBackendMessage(message)
    }
    socket.onerror = () => { backendConnected.value = false; websocketState.value = 'offline'; stopHeartbeat() }
    socket.onclose = () => {
      backendConnected.value = false
      streamStatus.value.obs = false
      websocketState.value = 'offline'
      stopHeartbeat()
      reconnectTimer = window.setTimeout(connectSocket, 3000)
    }
  }
  function startRealtimeEngine() {
    connectSocket()
    refreshChannelStatus()
  }
  async function sendMoodEvent(event) {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'mood_event', event }))
    try { mood.value = await api('/api/mood/event', { method: 'POST', body: JSON.stringify({ event }) }) } catch { simulateEvent(event) }
  }
  async function simulateViewerMessage(message = sandboxInput.value) {
    if (!message.trim()) return
    chat.value.push({ id: Date.now(), user: 'sandbox_viewer', message, color: '#00f5d4', badge: 'TEST', time: 'now' })
    try { await api('/api/sandbox/message', { method: 'POST', body: JSON.stringify({ viewer_name: 'sandbox_viewer', message }) }) } catch { appendLog('perception', 'heard') }
    sandboxInput.value = ''
  }
  function toggleStt() {
    if (sttListening.value) { recognition?.stop(); sttListening.value = false; return }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) { systemNotice.value = 'Р‘СЂР°СѓР·РµСЂ РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚ СЂР°СЃРїРѕР·РЅР°РІР°РЅРёРµ СЂРµС‡Рё'; return }
    recognition = new SpeechRecognition(); recognition.lang = 'ru-RU'; recognition.continuous = true; recognition.interimResults = false
    recognition.onresult = event => { const text = event.results[event.results.length - 1][0].transcript; transcript.value = text; api('/api/stream/stt', { method: 'POST', body: JSON.stringify({ transcript: text, language: 'ru-RU' }) }).catch(() => {}) }
    recognition.onend = () => { if (sttListening.value) recognition.start() }
    recognition.start(); sttListening.value = true
  }
  async function verifyProviderKey() {
    const provider = settings.value.llm_provider
    const apiKey = settings.value[`${provider}_api_key`] || ''
    try { await api('/api/llm/verify', { method: 'POST', body: JSON.stringify({ provider, api_key: apiKey }) }); providerStatus.value[provider] = 'active'; await saveSettings() } catch (error) {
      let detail = error.message
      try { detail = JSON.parse(error.message).detail || detail } catch {}
      providerStatus.value[provider] = `error:${detail}`
      systemNotice.value = `${provider}: ${detail}`
    }
  }
  async function refreshChannelStatus() {
    try {
      const status = await api('/api/twitch/status')
      channel.value = { login: status.channel || '', displayName: status.display_name || '', avatar: status.profile_image_url || '', live: Boolean(status.live), botUser: status.bot_user || '' }
      streamStatus.value.twitch = Boolean(status.connected)
    } catch { streamStatus.value.twitch = false }
  }
  async function checkSystem() {
    try {
      const health = await api('/health')
      const failed = Object.entries(health.services || {}).filter(([, value]) => value === false).map(([key]) => key)
      systemNotice.value = failed.length ? `РџСЂРѕРІРµСЂРєР°: РїСЂРѕР±Р»РµРјС‹ вЂ” ${failed.join(', ')}` : 'РџСЂРѕРІРµСЂРєР° СЃРёСЃС‚РµРјС‹: РІСЃС‘ РіРѕС‚РѕРІРѕ'
      return health
    } catch (error) {
      systemNotice.value = `РџСЂРѕРІРµСЂРєР° СЃРёСЃС‚РµРјС‹ РЅРµ СѓРґР°Р»Р°СЃСЊ: ${error.message}`
      return null
    }
  }
  async function panicStop() {
    muted.value = true
    queue.value = []
    overlayEvent.value = { type: 'BOT_STOP_TALKING' }
    try { await api('/api/overlay/stop', { method: 'POST' }) } catch { /* overlay is still hidden locally */ }
  }
  async function triggerMeme(imageUrl = '/uploads/demo-meme.png', soundUrl = '', duration = 5000) {
    const payload = { image_url: imageUrl, sound_url: soundUrl, duration }
    try { await api('/api/overlay/meme', { method: 'POST', body: JSON.stringify(payload) }) } catch { overlayEvent.value = { type: 'TRIGGER_MEME_FX', ...payload } }
  }
  setLanguage(language.value)
  return { language, activeNav, isLive, autoReply, tosGuard, autoScroll, preModeration, chat, logs, queue, mood, memories, filteredMemories, memoryQuery, memoryProfile, memoryProfiles, conversationMode, llmObservability, transcript, lastFrame, frameConfidence, backendConnected, websocketState, streamStatus, muted, channel, sandboxMode, sandboxInput, providerStatus, systemNotice, notifications, sttListening, visionDescription, accountMenuOpen, broadcasterToken, botToken, broadcasterUsername, broadcasterClientId, botUsername, botClientId, accountVerification, authNotice, settings, overlayEvent, frameDescription, setLanguage, setNav, setConversationMode, addMemoryProfile, toggleAccountMenu, openTwitchAuth, saveAccountTokens, syncBotNameFromAccount, setCustomBotName, verifyAccount, saveSettings, setLlmProvider, setRuntimeToggle, simulateEvent, sendMoodEvent, panicStop, triggerMeme, simulateViewerMessage, toggleStt, verifyProviderKey, refreshChannelStatus, refreshLlmObservability, checkSystem, approveQueue, editQueue, rejectQueue, sendQueueToJeet, removeQueue, addMemory, removeMemory, resetMemory, addChatMessage, loadPersistedState, startRealtimeEngine }
})
