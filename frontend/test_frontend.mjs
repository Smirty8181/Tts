import assert from 'node:assert/strict'
import fs from 'node:fs'

const source = fs.readFileSync(new URL('./src/stores/streamBotStore.js', import.meta.url), 'utf8')
const i18n = fs.readFileSync(new URL('./src/i18n/index.js', import.meta.url), 'utf8')
const app = fs.readFileSync(new URL('./src/App.vue', import.meta.url), 'utf8')

assert.match(i18n, /locale: 'en'/)
assert.match(i18n, /ru:/)
assert.match(source, /localStorage\.setItem\('stream-sentinel-language'/)
assert.match(source, /api\(`\/api\/queue\//)
assert.match(source, /new WebSocket/)
assert.match(app, /store\.activeNav/)
console.log('frontend smoke checks passed')
