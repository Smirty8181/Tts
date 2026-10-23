<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const visible = ref(false)
const text = ref('')
const displayedText = ref('')
const avatarState = ref('idle')
const viewerName = ref('')
const viewerPrompt = ref('')
const avatarPaths = ref({ idle: '', talking: '', rage: '', hype: '' })
let socket
let typingTimer
let hideTimer
let reconnectTimer
let mounted = false

const avatarSource = computed(() => avatarPaths.value[avatarState.value] || avatarPaths.value.idle)
const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function typeText(value) {
  clearInterval(typingTimer)
  displayedText.value = ''
  let index = 0
  typingTimer = window.setInterval(() => {
    displayedText.value = value.slice(0, index + 1)
    index += 1
    if (index >= value.length) clearInterval(typingTimer)
  }, 28)
}
function startTalking(message) {
  visible.value = true
  avatarState.value = message.avatar_state || 'talking'
  text.value = message.text || ''
  viewerName.value = message.viewer_name || ''
  viewerPrompt.value = message.prompt || ''
  typeText(text.value)
  clearTimeout(hideTimer)
  hideTimer = window.setTimeout(stopTalking, 12000)
}
function stopTalking() {
  visible.value = false
  clearInterval(typingTimer)
  hideTimer = window.setTimeout(() => { displayedText.value = ''; avatarState.value = 'idle' }, 450)
}
function handleMessage(event) {
  let message
  try { message = JSON.parse(event.data) } catch { return }
  if (message.type === 'BOT_START_TALKING') startTalking(message)
  if (message.type === 'BOT_STOP_TALKING') stopTalking()
  if (message.type === 'state') {
    avatarPaths.value = {
      idle: message.settings?.avatar_idle || '', talking: message.settings?.avatar_talking || '', rage: message.settings?.avatar_rage || '', hype: message.settings?.avatar_hype || ''
    }
  }
  if (message.type === 'AVATAR_UPDATED') avatarPaths.value[message.avatar_state] = message.path
}
function connect() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${(import.meta.env.VITE_BACKEND_URL || `${protocol}://${window.location.hostname}:8000`).replace(/^http/, 'ws')}/ws`)
  socket.onmessage = handleMessage
  socket.onclose = () => { if (mounted) reconnectTimer = window.setTimeout(connect, 3000) }
}
onMounted(() => { mounted = true; connect() })
onBeforeUnmount(() => { mounted = false; clearTimeout(hideTimer); clearInterval(typingTimer); clearTimeout(reconnectTimer); socket?.close() })
</script>

<template>
  <main class="obs-overlay" :class="{ 'is-visible': visible }">
    <div class="speech-bubble" aria-live="polite"><small v-if="viewerName">[ Viewer @{{ viewerName }} asked: ]</small><small v-if="viewerPrompt">“{{ viewerPrompt }}”</small>{{ displayedText }}<span class="typing-caret">|</span></div>
    <div class="obs-avatar" :class="`state-${avatarState}`">
      <img v-if="avatarSource" :src="avatarSource.startsWith('http') ? avatarSource : `${apiBase}${avatarSource}`" alt="Sentinel avatar" />
      <div v-else class="avatar-placeholder">S</div>
    </div>
  </main>
</template>

<style scoped>
.obs-overlay{position:fixed;inset:0;pointer-events:none;background:transparent;display:flex;align-items:flex-end;justify-content:flex-end;padding:40px;opacity:0;transform:translateY(50px);transition:opacity .45s ease,transform .55s cubic-bezier(.2,.8,.2,1)}.obs-overlay.is-visible{opacity:1;transform:translateY(0)}.obs-avatar{width:220px;height:280px;display:flex;align-items:flex-end;justify-content:center;filter:drop-shadow(0 16px 22px #0008)}.obs-avatar img{max-width:100%;max-height:100%;object-fit:contain}.avatar-placeholder{width:170px;height:210px;border-radius:90px 90px 28px 28px;background:linear-gradient(145deg,#9146ff,#27183f);border:2px solid #00f5d4;color:white;display:grid;place-items:center;font:bold 74px sans-serif}.state-rage{filter:drop-shadow(0 0 22px #ff4666)}.state-hype{filter:drop-shadow(0 0 22px #00f5d4)}.speech-bubble{max-width:420px;margin:0 12px 190px 0;padding:15px 18px;border:1px solid #00f5d488;border-radius:14px 14px 3px 14px;background:#111113e8;color:#fff;font:16px 'Space Grotesk',sans-serif;box-shadow:0 8px 28px #0008}.typing-caret{color:#00f5d4;animation:blink .8s infinite}@keyframes blink{50%{opacity:0}}
</style>
