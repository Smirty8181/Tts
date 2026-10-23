<script setup>
import { Activity, Flame, HeartHandshake, Laugh, Sparkles } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
const bars = [{ key: 'hype', icon: Flame, color: 'violet' }, { key: 'sarcasm', icon: Laugh, color: 'pink' }, { key: 'empathy', icon: HeartHandshake, color: 'cyan' }]
</script>
<template>
  <section class="panel mood-panel"><div class="panel-head"><div><div class="panel-title"><span class="icon-pink"><Activity :size="16" /></span>{{ $t('mood.title') }}</div><p>{{ $t('mood.subtitle') }}</p></div><span class="mood-badge" :class="store.mood.label">{{ $t(`mood.${store.mood.label}`) }}</span></div><div class="mood-bars"><div v-for="bar in bars" :key="bar.key" class="mood-bar"><div class="bar-label"><span><component :is="bar.icon" :size="14" />{{ $t(`mood.${bar.key}`) }}</span><b>{{ store.mood[bar.key] }}%</b></div><div class="progress-track"><i :class="bar.color" :style="{ width: `${store.mood[bar.key]}%` }"></i></div></div></div></section>
</template>
