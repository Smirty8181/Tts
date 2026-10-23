<script setup>
import { computed, ref } from 'vue'
import { Database, Plus, Search, Trash2 } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'
const store = useStreamBotStore()
const newProfile = ref('')
const profileOptions = computed(() => store.memoryProfiles)
function createProfile() {
  store.addMemoryProfile(newProfile.value)
  newProfile.value = ''
}
</script>
<template>
  <section class="panel memory-panel">
    <div class="panel-head"><div><div class="panel-title"><span class="icon-purple"><Database :size="16" /></span>Память Sentinel</div><p>Профили, лор и важные моменты эфира</p></div><button class="tiny-add" @click="store.addMemory(store.memoryProfile === 'all' ? 'NOTE' : store.memoryProfile.toUpperCase())"><Plus :size="14" /></button></div>
    <div class="memory-toolbar"><div class="memory-search"><Search :size="14" /><input v-model="store.memoryQuery" placeholder="Поиск в памяти..." /></div><select v-model="store.memoryProfile"><option v-for="profile in profileOptions" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></div>
    <div class="profile-create"><input v-model="newProfile" placeholder="Новый профиль" @keyup.enter="createProfile" /><button @click="createProfile">Добавить</button></div>
    <div class="memory-items"><div v-for="memory in store.filteredMemories" :key="memory.id" class="memory-item"><span>{{ memory.type }}</span><p>{{ memory.value }}</p><button :aria-label="`Удалить ${memory.value}`" @click="store.removeMemory(memory.id)"><Trash2 :size="13" /></button></div><div v-if="!store.filteredMemories.length" class="empty-state">Память не найдена</div></div>
  </section>
</template>
