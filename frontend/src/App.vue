<script setup>
import { onMounted, ref } from 'vue'
import { useStreamBotStore } from './stores/streamBotStore'
import Sidebar from './components/Sidebar.vue'
import Header from './components/Header.vue'
import VisionInspector from './components/VisionInspector.vue'
import ChatMonitor from './components/ChatMonitor.vue'
import DecisionLogs from './components/DecisionLogs.vue'
import MoodEngine from './components/MoodEngine.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ObsOverlay from './views/ObsOverlay.vue'
import AccountManagerModal from './components/AccountManagerModal.vue'
import AuthCallback from './views/AuthCallback.vue'
import MemeOverlay from './views/MemeOverlay.vue'
import RuntimePanel from './components/RuntimePanel.vue'
import MemoryPanel from './components/MemoryPanel.vue'

const store = useStreamBotStore()
const showAccountManager = ref(false)
const isOverlay = window.location.pathname === '/overlay/avatar' || window.location.pathname === '/overlay/box'
const isMemeOverlay = window.location.pathname === '/overlay/memes'
const isAuthCallback = window.location.pathname === '/auth/callback'
onMounted(async () => {
  await store.loadPersistedState()
  await store.refreshLlmObservability()
  store.startRealtimeEngine()
})
</script>

<template>
  <ObsOverlay v-if="isOverlay" />
  <MemeOverlay v-else-if="isMemeOverlay" />
  <AuthCallback v-else-if="isAuthCallback" />
  <div v-else class="app-shell">
    <div v-if="store.systemNotice" class="system-toast" @click="store.systemNotice = ''">{{ store.systemNotice }}</div>
    <div v-if="store.notifications.length" class="notification-stack">
      <div v-for="notice in store.notifications.slice(0, 4)" :key="notice.id" class="notification-card" :class="`notification-${notice.level}`">
        <strong>{{ notice.level === 'error' ? 'Ошибка' : notice.level === 'warning' ? 'Предупреждение' : notice.level === 'reconnect' ? 'Переподключение' : 'Готово' }}</strong>
        <span>{{ notice.message }}</span>
      </div>
    </div>
    <Sidebar @open-account="showAccountManager = true" />
    <main class="main-shell">
      <Header />
      <div class="content-wrap">
        <section class="page-intro">
          <div><span class="eyebrow">{{ store.streamStatus.twitch ? $t('common.live') : $t('common.offline') }} / {{ $t('nav.overview') }}</span><h1>{{ $t('header.title') }}</h1><p>{{ $t('header.subtitle') }} <span class="pulse-dot"></span> {{ store.backendConnected ? $t('common.online') : $t('common.offline') }}</p></div>
          <div class="intro-stats"><div><strong>{{ store.backendConnected ? 'OK' : '—' }}</strong><small>Backend</small></div><div><strong>{{ store.streamStatus.twitch ? 'OK' : '—' }}</strong><small>Twitch IRC</small></div><div><strong>{{ store.streamStatus.obs ? 'OK' : '—' }}</strong><small>OBS</small></div></div>
        </section>
        <Transition name="view" mode="out-in"><div :key="store.activeNav" class="dashboard-grid">
          <template v-if="store.activeNav === 'overview'"><VisionInspector /><ChatMonitor /><RuntimePanel /><MemoryPanel /><DecisionLogs /><MoodEngine /><SettingsPanel /></template>
          <VisionInspector v-else-if="store.activeNav === 'perception'" />
          <ChatMonitor v-else-if="store.activeNav === 'chat'" />
          <DecisionLogs v-else-if="store.activeNav === 'decisions'" />
          <MoodEngine v-else-if="store.activeNav === 'mood'" />
          <SettingsPanel v-else-if="store.activeNav === 'settings'" />
        </div></Transition>
      </div>
    </main>
    <AccountManagerModal v-if="showAccountManager || store.accountMenuOpen" @close="showAccountManager = false" />
  </div>
</template>
