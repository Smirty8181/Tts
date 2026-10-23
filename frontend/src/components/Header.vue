<script setup>
import { Languages, ShieldCheck, Siren, Zap } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
</script>
<template>
  <header class="topbar"><div class="breadcrumb"><span>{{ $t('common.workspace') }}</span><b>/</b><strong>{{ $t(`nav.${store.activeNav}`) }}</strong></div><div class="top-statuses"><span><i :class="store.streamStatus.obs ? 'ok' : 'bad'"></i> OBS WebSocket</span><span><i :class="store.streamStatus.twitch ? 'ok' : 'bad'"></i> {{ store.streamStatus.twitch ? '🟢 Twitch IRC Подключен' : '🔴 Twitch IRC Отключен' }}</span></div><div class="top-actions"><button class="panic-button" @click="store.panicStop"><Siren :size="14" /> {{ $t('header.panic') }}</button><button class="top-toggle" :class="{ on: store.tosGuard }" @click="store.setRuntimeToggle('tos_guard', !store.tosGuard)"><ShieldCheck :size="15" /> {{ $t('header.guard') }} <span></span></button><button class="top-toggle" :class="{ on: store.autoReply }" @click="store.setRuntimeToggle('auto_reply', !store.autoReply)"><Zap :size="15" /> {{ $t('header.autoReply') }} <span></span></button><div class="lang-switch"><Languages :size="15" /><button :class="{ selected: store.language === 'en' }" @click="store.setLanguage('en')">EN</button><button :class="{ selected: store.language === 'ru' }" @click="store.setLanguage('ru')">RU</button></div><button class="header-avatar gradient-avatar" :aria-label="$t('header.account')" @click="store.toggleAccountMenu()">{{ store.settings.bot_name?.slice(0, 1) || '?' }}</button></div></header>
</template>
