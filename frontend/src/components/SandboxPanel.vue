<script setup>
import { FlaskConical, Send, Zap } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
function toggle(value) { store.sandboxMode = value; localStorage.setItem('stream-sentinel-sandbox', String(value)) }
</script>
<template>
  <section class="panel sandbox-panel"><div class="panel-head"><div><div class="panel-title"><span class="icon-amber"><FlaskConical :size="16" /></span>Режим тестирования</div><p>Проверяйте команды и ответы без запущенного стрима.</p></div><button class="sandbox-toggle" :class="{ selected: store.sandboxMode }" @click="toggle(!store.sandboxMode)"><span></span>{{ store.sandboxMode ? 'Включён' : 'Выключен' }}</button></div><div class="sandbox-body"><label>Симулировать сообщение от зрителя<input v-model="store.sandboxInput" @keyup.enter="store.simulateViewerMessage()" placeholder="!askbot Привет, бот!" /></label><button class="sandbox-send" :disabled="!store.sandboxMode" @click="store.simulateViewerMessage"><Send :size="14" /> Отправить</button><div class="sandbox-quick"><button :disabled="!store.sandboxMode" @click="store.simulateViewerMessage('!askbot Оцени этот момент')"><Zap :size="13" /> !askbot</button><button :disabled="!store.sandboxMode" @click="store.simulateViewerMessage('!challenge Сделай вызов')"><Zap :size="13" /> !challenge</button><button :disabled="!store.sandboxMode" @click="store.triggerMeme()">🎬 Мем / FX</button></div></div></section>
</template>
