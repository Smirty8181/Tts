<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
const active = ref(null)
const progress = ref(0)
let socket
let timer
let progressTimer
let reconnectTimer
let mounted = false
const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'
function trigger(event) {
  active.value = event
  progress.value = 0
  clearTimeout(timer); clearInterval(progressTimer)
  if (event.sound_url) new Audio(event.sound_url.startsWith('http') ? event.sound_url : `${apiBase}${event.sound_url}`).play().catch(() => {})
  const duration = event.duration || 5000
  progressTimer = window.setInterval(() => { progress.value += 100 / (duration / 100); if (progress.value >= 100) clearInterval(progressTimer) }, 100)
  timer = window.setTimeout(() => { active.value = null }, duration)
}
function connect() { const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'; socket = new WebSocket(`${(import.meta.env.VITE_BACKEND_URL || `${protocol}://${window.location.hostname}:8000`).replace(/^http/, 'ws')}/ws`); socket.onmessage = event => { try { const message = JSON.parse(event.data); if (message.type === 'TRIGGER_MEME_FX') trigger(message) } catch {} }; socket.onclose = () => { if (mounted) reconnectTimer = window.setTimeout(connect, 3000) } }
onMounted(() => { mounted = true; connect() })
onBeforeUnmount(() => { mounted = false; clearTimeout(timer); clearInterval(progressTimer); clearTimeout(reconnectTimer); socket?.close() })
</script>
<template><main class="meme-overlay"><Transition name="meme"><div v-if="active" class="meme-card"><img :src="active.image_url.startsWith('http') ? active.image_url : `${apiBase}${active.image_url}`" alt="Meme effect" /><div class="meme-progress"><i :style="{ width: `${progress}%` }"></i></div></div></Transition></main></template>
<style scoped>.meme-overlay{position:fixed;inset:0;display:grid;place-items:center;background:transparent;pointer-events:none}.meme-card{max-width:80vw;max-height:80vh;filter:drop-shadow(0 18px 28px #0009)}.meme-card img{display:block;max-width:100%;max-height:70vh;object-fit:contain}.meme-progress{height:5px;margin-top:12px;background:#222;border-radius:4px;overflow:hidden}.meme-progress i{display:block;height:100%;background:#00f5d4}.meme-enter-active{animation:meme-in .45s cubic-bezier(.2,1.6,.3,1)}.meme-leave-active{animation:meme-out .35s ease}@keyframes meme-in{from{opacity:0;transform:scale(.3) rotate(-8deg)}to{opacity:1;transform:scale(1) rotate(0)}}@keyframes meme-out{to{opacity:0;transform:scale(.8)}}
</style>
