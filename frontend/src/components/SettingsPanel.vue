<script setup>
import { computed, ref } from 'vue'
import { Bot, Clipboard, Database, Eye, EyeOff, ExternalLink, KeyRound, Link2, Plus, RotateCcw, Save, SlidersHorizontal, Trash2, Twitch, Upload, Volume2, Webhook } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'

const store = useStreamBotStore()
const providers = [{ key: 'gemini', name: 'Google Gemini', url: 'https://aistudio.google.com/app/apikey', note: 'Create a free key in AI Studio.' }, { key: 'groq', name: 'Groq', url: 'https://console.groq.com/keys', note: 'Use the Groq API console.' }, { key: 'deepseek', name: 'DeepSeek', url: 'https://platform.deepseek.com/api_keys', note: 'Generate an API key in the DeepSeek dashboard.' }, { key: 'openai', name: 'OpenAI', url: 'https://platform.openai.com/api-keys', note: 'Create a restricted API key.' }]
const modelOptions = {
  gemini: ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'],
  groq: ['openai/gpt-oss-20b', 'llama-3.3-70b-versatile', 'llama-3.1-8b-instant'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  openai: ['gpt-4o-mini', 'gpt-4o']
}
const avatarStates = ['idle', 'talking', 'rage', 'hype']
const avatarLabels = { idle: 'Покой (Idle)', talking: 'Разговор (Talking)', rage: 'Злость / Раж (Rage)', hype: 'Восторг / Хайп (Hype)' }
const activeProvider = computed(() => providers.find(provider => provider.key === store.settings.llm_provider) || providers[0])
const uploadState = ref('')
const testState = ref('')
const obsMode = ref(localStorage.getItem('stream-sentinel-overlay-mode') || 'auto-hide')
const copied = ref(false)
const previewState = ref('idle')
const showProviderKey = ref(false)
const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const obsUrl = computed(() => `${window.location.origin}/overlay/avatar`)

function setObsMode(mode) { obsMode.value = mode; localStorage.setItem('stream-sentinel-overlay-mode', mode) }
async function copyObsLink() { await navigator.clipboard.writeText(obsUrl.value); copied.value = true; window.setTimeout(() => { copied.value = false }, 2200) }
async function previewAvatar() {
  previewState.value = 'talking'
  try { await fetch(`${apiBase}/api/overlay/speak`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: 'Привет! Это тест анимации аватара.', avatar_state: 'talking' }) }) } catch { store.overlayEvent = { type: 'BOT_START_TALKING', text: 'Привет! Это тест анимации аватара.', avatar_state: 'talking' } }
  window.setTimeout(async () => { previewState.value = 'idle'; try { await fetch(`${apiBase}/api/overlay/stop`, { method: 'POST' }) } catch {} }, 4000)
}
async function uploadAvatar(event, state) { const file = event.target.files?.[0]; if (!file) return; const formData = new FormData(); formData.append('file', file); uploadState.value = `Загрузка: ${avatarLabels[state]}`; try { const response = await fetch(`${apiBase}/api/settings/avatar/${state}`, { method: 'POST', body: formData }); if (!response.ok) throw new Error('Не удалось загрузить файл'); uploadState.value = 'Аватар сохранён' } catch (error) { uploadState.value = error.message } }
async function testJeetBot() { testState.value = 'Тест отправляется...'; try { const response = await fetch(`${apiBase}/api/overlay/speak`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: 'Sentinel онлайн.', avatar_state: 'talking' }) }); if (!response.ok) throw new Error('JeetBot недоступен'); window.setTimeout(() => fetch(`${apiBase}/api/overlay/stop`, { method: 'POST' }), 4000); testState.value = 'Тест отправлен' } catch (error) { testState.value = error.message } }
const providerKey = computed(() => `${store.settings.llm_provider}_api_key`)
const providerPlaceholder = computed(() => ({ gemini: 'AIzaSy...', groq: 'gsk_...', deepseek: 'sk-...', openai: 'sk-proj-...' }[store.settings.llm_provider]))
const selectedModel = computed({
  get: () => store.settings[`${store.settings.llm_provider}_model`] || modelOptions[store.settings.llm_provider]?.[0] || '',
  set: value => { store.settings[`${store.settings.llm_provider}_model`] = value }
})
const activeModels = computed(() => modelOptions[store.settings.llm_provider] || [])
</script>

<template>
  <section class="panel settings-panel">
    <div class="panel-head"><div><div class="panel-title"><span class="icon-green"><SlidersHorizontal :size="16" /></span>{{ $t('settings.title') }}</div><p>{{ $t('settings.helper') }}</p></div><button class="save-button" @click="store.saveSettings()"><Save :size="14" /> {{ $t('common.save') }}</button></div>
    <div class="settings-grid">
      <div class="settings-column"><div class="setting-section-title"><Bot :size="15" /> Характер и стиль общения</div><div class="preset-row"><button v-for="preset in ['🎭 Саркастичный тролль', '🌶️ Без цензуры', '🤬 Геймер в раже', '💛 Дружелюбный помощник']" :key="preset" @click="store.settings.system_prompt = preset">{{ preset }}</button></div><label>Имя бота<input v-model="store.settings.bot_name" placeholder="Например: JeetBot" /></label><label>На какие обращения отвечать <small>Укажите слова через запятую</small><input :value="store.settings.response_triggers.join(', ')" placeholder="Зетка, Зеточка, НейроЗетка, neyrozetka, Зет" @input="store.settings.response_triggers = $event.target.value.split(',').map(item => item.trim()).filter(Boolean)" /></label><label>Системный промпт (Инструкция для ИИ)<textarea v-model="store.settings.system_prompt"></textarea></label><div class="control-row"><label>Креативность / Дёрзость<div class="range-line"><input v-model="store.settings.temperature" type="range" min=".2" max="1" step=".01" /><b>{{ store.settings.temperature <= .4 ? 'Консервативный' : store.settings.temperature <= .75 ? 'Баланс' : 'Безумный / Творческий' }}</b></div></label><label>Частота ответов в чат<div class="range-line"><input v-model="store.settings.cooldown" type="range" min="2" max="15" step="1" /><b>{{ store.settings.cooldown <= 4 ? 'Каждые 2 сек' : store.settings.cooldown <= 8 ? 'Каждые 5 сек' : 'Раз в 15 сек' }}</b></div></label></div><div class="setting-section-title provider-title"><Bot :size="15" /> Основная нейросеть (LLM)</div>      <div class="provider-tabs"><button v-for="provider in providers" :key="provider.key" type="button" :class="{ selected: store.settings.llm_provider === provider.key }" @click="store.setLlmProvider(provider.key)">{{ provider.name }}</button></div><label class="model-select">Модель<select v-model="selectedModel" @change="store.saveSettings({ [`${store.settings.llm_provider}_model`]: selectedModel })"><option v-for="model in activeModels" :key="model" :value="model">{{ model }}</option></select></label><div class="provider-key-card"><label>API ключ {{ activeProvider.name }}<div class="key-input-row"><input v-model="store.settings[providerKey]" :type="showProviderKey ? 'text' : 'password'" :placeholder="providerPlaceholder" /><button type="button" @click="showProviderKey = !showProviderKey"><EyeOff v-if="showProviderKey" :size="15" /><Eye v-else :size="15" /></button></div></label><a :href="activeProvider.url" target="_blank" rel="noreferrer">🔗 Получить API ключ</a><button class="verify-key-button" @click="store.verifyProviderKey">Проверить и сохранить ключ</button><span v-if="store.providerStatus[store.settings.llm_provider] === 'active'" class="key-status active">🟢 API ключ активен и работает</span><span v-else-if="store.providerStatus[store.settings.llm_provider] === 'error'" class="key-status error">🔴 Ошибка: Неверный API ключ</span></div></div>
      <div class="settings-column"><div class="setting-section-title"><Webhook :size="15" /> {{ $t('settings.jeetbot') }} <span class="toggle-on">ON</span></div><label>{{ $t('settings.endpoint') }}<div class="input-icon"><Webhook :size="13" /><input v-model="store.settings.jeetbot_endpoint" placeholder="https://..." /></div></label><button class="copy-webhook" @click="navigator.clipboard.writeText(store.settings.jeetbot_endpoint)"><Clipboard :size="13" /> Скопировать Webhook URL</button><div class="control-row"><label>{{ $t('settings.voice') }}<select v-model="store.settings.voice_id"><option>JEE-02 · Nova</option><option>JEE-07 · Warm</option></select></label><label>{{ $t('settings.speed') }}<div class="range-line"><input v-model="store.settings.speed" type="range" min=".5" max="2" step=".05" /><b>{{ store.settings.speed }}x</b></div></label></div><button class="test-jeet" @click="testJeetBot"><Volume2 :size="14" /> Test JeetBot speech</button><small class="feedback-text">{{ testState }}</small><div class="setting-section-title memory-title"><Database :size="15" /> {{ $t('settings.memory') }} <button class="tiny-add" @click="store.addMemory"><Plus :size="13" /></button></div><div class="memory-list"><div v-for="memory in store.memories" :key="memory.id"><span>{{ memory.type }}</span><p>{{ memory.value }}</p><button @click="store.removeMemory(memory.id)"><Trash2 :size="13" /></button></div></div><div class="memory-actions"><button @click="store.addMemory"><Plus :size="13" /> {{ $t('settings.add') }}</button><button @click="store.resetMemory"><RotateCcw :size="13" /> {{ $t('settings.reset') }}</button></div></div>
    </div>
    <div class="obs-control-card">
      <div class="setting-section-title"><Eye :size="15" /> OBS WebSocket 5.x</div>
      <div class="control-row">
        <label>Адрес OBS<input v-model="store.settings.obs_url" placeholder="ws://127.0.0.1:4455" /></label>
        <label>Пароль OBS<input v-model="store.settings.obs_password" type="password" placeholder="Необязательно" /></label>
      </div>
      <label class="obs-enable"><input v-model="store.settings.obs_enabled" type="checkbox" /> Подключать OBS автоматически</label>
      <button class="verify-key-button" @click="store.saveSettings()">Сохранить OBS-настройки</button>
    </div>
    <div class="obs-embed-card"><div class="obs-embed-heading"><div><div class="setting-section-title"><Eye :size="15" /> OBS Stream Overlay</div><p>Вставьте эту ссылку в OBS -> Источники -> Браузер (Browser Source). Рекомендуемый размер: 600x800 или 1920x1080.</p></div><span class="obs-badge">BROWSER SOURCE</span></div><div class="obs-link-row"><input :value="obsUrl" readonly /><button class="copy-obs-button" @click="copyObsLink"><Clipboard :size="15" /> Скопировать ссылку для OBS</button></div><small v-if="copied" class="copy-toast">Ссылка скопирована!</small><div class="overlay-mode"><b>Режим overlay</b><button :class="{ selected: obsMode === 'auto-hide' }" @click="setObsMode('auto-hide')">Auto-Hide <small>Скрыт в тишине</small></button><button :class="{ selected: obsMode === 'always-visible' }" @click="setObsMode('always-visible')">Always Visible <small>Idle всегда виден</small></button></div></div>
    <div class="avatar-settings"><div class="avatar-settings-head"><div><div class="setting-section-title"><Upload :size="15" /> Состояния аватара OBS</div><p>Загрузите изображения (PNG, GIF, JPEG, WebP) с прозрачным фоном для браузерного источника OBS.</p></div><button class="preview-avatar-button" @click="previewAvatar"><Eye :size="14" /> Предпросмотр аватара</button></div><div class="avatar-upload-grid"><label v-for="state in avatarStates" :key="state" class="avatar-upload"><span>{{ avatarLabels[state] }}</span><input type="file" accept="image/png,image/gif,image/jpeg,image/webp" @change="uploadAvatar($event, state)" /><Upload :size="16" /><small>Выбрать файл</small></label></div><div class="avatar-mini-preview" :class="`preview-${previewState}`"><div class="avatar-mini-shape">S</div><span v-if="previewState === 'talking'">Привет! Тест речи</span></div><small class="feedback-text">{{ uploadState }}</small></div>
    <div class="api-helper-grid"><div class="helper-card twitch-help"><Twitch :size="18" /><div><b>Официальная авторизация Twitch</b><p>Используйте кнопку «Войти через Twitch» и scopes <strong>chat:read</strong>, <strong>chat:edit</strong>.</p><a href="https://dev.twitch.tv/docs/authentication/getting-tokens/" target="_blank" rel="noreferrer"><Link2 :size="13" /> Открыть документацию OAuth</a></div></div><div class="helper-card"><KeyRound :size="18" /><div><b>JeetBot setup</b><p>Copy your webhook and voice ID from the official service dashboard.</p><a href="https://jeetbot.ru/" target="_blank" rel="noreferrer"><ExternalLink :size="13" /> Open JeetBot</a></div></div></div>
  </section>
</template>
