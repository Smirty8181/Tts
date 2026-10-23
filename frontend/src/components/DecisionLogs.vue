<script setup>
import { computed, ref } from 'vue'
import { Brain, ChevronDown, CircleAlert, Eye, GitBranch, ShieldCheck, Volume2 } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore(); const filter = ref('all')
const filters = ['all', 'perception', 'reasoning', 'action', 'safety']
const filteredLogs = computed(() => filter.value === 'all' ? store.logs : store.logs.filter(log => log.type === filter.value))
const icons = { perception: Eye, reasoning: GitBranch, action: Volume2, safety: ShieldCheck }
</script>
<template>
  <section class="panel logs-panel"><div class="panel-head"><div><div class="panel-title"><span class="icon-orange"><Brain :size="16" /></span>{{ $t('logs.title') }}</div><p>{{ $t('logs.subtitle') }}</p></div><span class="streaming-label"><i></i> STREAMING</span></div><div class="log-tabs"><button v-for="item in filters" :key="item" :class="{ selected: filter === item }" @click="filter = item">{{ $t(`logs.${item}`) }}</button></div><div class="log-list"><div v-for="log in filteredLogs" :key="log.id" class="log-row"><div class="log-icon" :class="log.type"><component :is="icons[log.type] || CircleAlert" :size="14" /></div><div class="log-copy"><div><span>{{ $t(`logs.${log.type}`) }}</span><time>{{ log.time }}</time></div><p>{{ $t(`logsText.${log.textKey}`) }}</p></div></div></div></section>
</template>
