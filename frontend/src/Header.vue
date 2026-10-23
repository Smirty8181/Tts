<script setup>
import { Languages, ShieldCheck, Zap } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
</script>
<template>
  <header class="topbar"><div class="breadcrumb"><span>WORKSPACE</span><b>/</b><strong>{{ $t(`nav.${store.activeNav}`) }}</strong></div><div class="top-actions"><button class="top-toggle" :class="{ on: store.tosGuard }" @click="store.tosGuard = !store.tosGuard"><ShieldCheck :size="15" /> {{ $t('header.guard') }} <span></span></button><button class="top-toggle" :class="{ on: store.autoReply }" @click="store.autoReply = !store.autoReply"><Zap :size="15" /> {{ $t('header.autoReply') }} <span></span></button><div class="lang-switch"><Languages :size="15" /><button :class="{ selected: store.language === 'en' }" @click="store.setLanguage('en')">EN</button><button :class="{ selected: store.language === 'ru' }" @click="store.setLanguage('ru')">RU</button></div><div class="header-avatar gradient-avatar">M</div></div></header>
</template>
