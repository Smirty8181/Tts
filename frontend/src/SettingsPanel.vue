<script setup>
import { Bot, Database, KeyRound, Plus, RotateCcw, Save, SlidersHorizontal, Trash2, Twitch, Webhook } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
</script>
<template>
  <section class="panel settings-panel"><div class="panel-head"><div><div class="panel-title"><span class="icon-green"><SlidersHorizontal :size="16" /></span>{{ $t('settings.title') }}</div><p>{{ $t('settings.helper') }}</p></div><button class="save-button"><Save :size="14" /> {{ $t('common.save') }}</button></div></section>
</template>
