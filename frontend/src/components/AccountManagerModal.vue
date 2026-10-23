<script setup>
import { ExternalLink, KeyRound, LogIn, Save, ShieldCheck, Twitch, UserRound, X } from 'lucide-vue-next'
import { useStreamBotStore } from '../stores/streamBotStore'

const emit = defineEmits(['close'])
const store = useStreamBotStore()

function close() {
  store.accountMenuOpen = false
  emit('close')
}
</script>

<template>
  <div class="modal-backdrop" @click.self="close">
    <section class="account-modal" role="dialog" aria-modal="true" :aria-label="$t('header.account')">
      <header class="account-modal-header">
        <div class="account-modal-title"><span class="account-modal-icon"><Twitch :size="17" /></span><div><h2>{{ $t('header.account') }}</h2><p>{{ $t('header.oauth') }}</p></div></div>
        <button class="modal-close" type="button" :aria-label="$t('common.close')" @click="close"><X :size="18" /></button>
      </header>

      <div class="account-block">
        <div class="account-block-title"><UserRound :size="15" /> {{ $t('settings.broadcaster') }}</div>
        <button class="twitch-login-button" type="button" @click="store.openTwitchAuth('broadcaster')"><LogIn :size="15" /> Войти через Twitch</button>
        <p class="account-helper">Разрешите доступ в Twitch — аккаунт подключится и сохранится автоматически.</p>
        <p v-if="store.accountVerification.broadcaster" class="account-feedback" :class="{ error: store.accountVerification.broadcasterError }">{{ store.accountVerification.broadcaster }}</p>
        <p v-if="store.authNotice" class="account-feedback error">{{ store.authNotice }}</p>
      </div>

      <div class="account-block">
        <div class="account-block-title"><UserRound :size="15" /> Аккаунт бота</div>
        <p class="account-helper">Введите только ник бота и Access Token. Client ID приложения настраивается на сервере.</p>
        <label>{{ $t('account.username') }}<input v-model="store.botUsername" @input="store.syncBotNameFromAccount" autocomplete="off" placeholder="Введите логин бота" /></label>
        <label>Access Token<input v-model="store.botToken" type="password" autocomplete="off" placeholder="oauth:... или токен без oauth:" /></label>
        <p class="account-helper">Нужны права <strong>chat:read</strong> и <strong>chat:edit</strong>.</p>
        <button class="twitch-connect-button" type="button" @click="store.verifyAccount('bot')"><ShieldCheck :size="15" /> Проверить и подключить бота</button>
        <p v-if="store.accountVerification.bot" class="account-feedback" :class="{ error: store.accountVerification.botError }">{{ store.accountVerification.bot }}</p>
      </div>

      <footer class="account-modal-footer"><div><KeyRound :size="14" /><span>{{ $t('account.localNotice') }}</span></div><button class="save-account-button" type="button" @click="store.saveAccountTokens(); close()"><Save :size="15" /> {{ $t('header.saveAccount') }}</button></footer>
    </section>
  </div>
</template>
