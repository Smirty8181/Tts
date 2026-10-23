<script setup>
import { Activity, BrainCircuit, Radio, ShieldCheck, Sparkles } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
const modes = [
  { id: 'balanced', label: 'Баланс', hint: 'Умный темп' },
  { id: 'listener', label: 'Наблюдатель', hint: 'Отвечает редко' },
  { id: 'hype', label: 'Хайп', hint: 'Больше энергии' }
]
</script>
<template>
  <section class="panel runtime-panel">
    <div class="panel-head"><div><div class="panel-title"><span class="icon-cyan"><Activity :size="16" /></span>Режим общения</div><p>Быстрый контроль поведения Sentinel в эфире</p></div><span class="live-chip small"><span class="status-dot"></span> {{ store.streamStatus.twitch ? 'LIVE' : 'OFFLINE' }}</span></div>
    <div class="mode-cards"><button v-for="mode in modes" :key="mode.id" :class="{ selected: store.conversationMode === mode.id }" @click="store.setConversationMode(mode.id)"><strong>{{ mode.label }}</strong><small>{{ mode.hint }}</small></button></div>
    <div class="status-grid">
      <div><Radio :size="14" /><span>OBS WebSocket</span><b :class="store.streamStatus.obs ? 'status-good' : 'status-muted'">{{ store.streamStatus.obs ? 'Подключён' : 'Ожидание' }}</b></div>
      <div><BrainCircuit :size="14" /><span>AI pipeline</span><b :class="store.backendConnected ? 'status-good' : 'status-muted'">{{ store.backendConnected ? 'Синхронно' : 'Ожидание backend' }}</b></div>
      <div><ShieldCheck :size="14" /><span>TOS Guard</span><b class="status-good">{{ store.tosGuard ? 'Активен' : 'Выключен' }}</b></div>
      <div><Sparkles :size="14" /><span>Профиль</span><b>{{ store.mood.label }}</b></div>
    </div>
    <div class="observability-strip">
      <div class="observability-title">Состояние системы <button @click="store.checkSystem">Проверить всё</button></div>
      <div class="observability-title">LLM наблюдаемость <button @click="store.refreshLlmObservability">Обновить</button></div>
      <div v-if="store.llmObservability.length" class="observation-list">
        <div v-for="item in store.llmObservability.slice(0, 3)" :key="`${item.created_at}-${item.provider}`">
          <span :class="item.success ? 'status-good' : 'status-error'">{{ item.success ? '●' : '●' }}</span>
          <b>{{ item.provider }}</b><span>{{ item.mode }}</span><strong>{{ item.latency_ms }} ms</strong>
        </div>
      </div>
      <small v-else>Пока нет завершённых вызовов LLM</small>
    </div>
  </section>
</template>
