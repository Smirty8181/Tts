<script setup>
import { computed } from 'vue'
import { Activity, BrainCircuit, ChevronDown, Eye, Gauge, MessageSquare, Radio, Settings2, Sparkles } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
const items = computed(() => [
  { key: 'overview', icon: Gauge }, { key: 'perception', icon: Eye }, { key: 'chat', icon: MessageSquare }, { key: 'decisions', icon: BrainCircuit }, { key: 'mood', icon: Sparkles }, { key: 'settings', icon: Settings2 }
])
</script>
<template>
  <aside class="sidebar">
    <div class="brand"><div class="brand-mark"><Radio :size="19" /></div><div><strong>SENTINEL</strong><small>AI STREAM OS</small></div></div>
    <button class="channel-switcher" :aria-label="$t('header.account')" @click="store.toggleAccountMenu()"><div class="avatar gradient-avatar"><img v-if="store.channel.avatar" :src="store.channel.avatar" alt="" /></div><div><strong>{{ store.channel.displayName || store.channel.login || $t('accounts.noChannel') }}</strong><small><span class="status-dot"></span> {{ store.channel.live ? $t('accounts.live') : $t('accounts.offline') }}</small></div><ChevronDown :size="15" /></button>
    <nav><button v-for="item in items" :key="item.key" class="nav-item" :class="{ active: store.activeNav === item.key }" @click="store.setNav(item.key)"><component :is="item.icon" :size="17" /><span>{{ $t(`nav.${item.key}`) }}</span><i v-if="item.key === 'chat' && store.queue.length" class="nav-count">{{ store.queue.length }}</i></button></nav>
    <div class="sidebar-foot"><div class="mini-profile"><div class="avatar bot-avatar">{{ store.settings.bot_name?.slice(0, 1) || '?' }}</div><div><strong>{{ store.settings.bot_name || '—' }}</strong><small>{{ store.backendConnected ? $t('common.online') : $t('common.offline') }}</small></div><span class="online-ring" :class="{ offline: !store.backendConnected }"></span></div><div class="account-mini"><span class="status-dot" :class="{ offline: !store.backendConnected }"></span><span>{{ store.backendConnected ? $t('common.online') : $t('common.offline') }}</span></div></div>
  </aside>
</template>
