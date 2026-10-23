import asyncio
import json
import logging
import time
import hashlib
from collections import deque
from pathlib import Path
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Account, ChatMemory, Log, LlmObservation, Memory, Mood, PersonaSettings, QueueItem, SessionLocal, StreamerProfile, ViewerMessage, ViewerProfile, decrypt, encrypt, init_db
from app.services.gemini_service import GeminiService
from app.services.jeetbot_service import JeetBotService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.twitch_service import TwitchService
from app.services.twitch_verify_service import TwitchVerificationError, verify_twitch_credentials
from app.services.deepseek_service import DeepSeekError, generate_reply
from app.services.gemini_verification import GeminiVerificationError, verify_gemini_api_key
from app.services.llm_provider_service import LlmProviderError, generate_provider_reply, verify_provider_key
from app.monitors.chat import WAKE_WORDS, ViewerCommand, extract_wake_word, parse_viewer_command
from app.services.context_service import build_context, sanitize_viewer_message, deterministic_summary
from app.services.obs_service import ObsService
from app.services.speech_service import SpeechService

logger = logging.getLogger(__name__)
settings = get_settings()
DEFAULT_TWITCH_CLIENT_ID = 'gragq9yg68pkionhexl3zlgca9rj2p'
mood_service = MoodService()
memory_service = MemoryService()
twitch_service = TwitchService(settings)
gemini_service = GeminiService(settings)
jeetbot_service = JeetBotService(settings)
obs_service = ObsService()
speech_service = SpeechService()
irc_task = None
irc_started_at = 0.0
irc_reconnect_lock = asyncio.Lock()
recent_streamer_transcripts: deque[str] = deque(maxlen=8)
last_vision_hash = ''
last_vision_description = ''
vision_events = {'death', 'victory', 'scene_change', 'meme', 'screen_change'}
llm_semaphore = asyncio.Semaphore(4)
vision_semaphore = asyncio.Semaphore(1)
viewer_locks: dict[str, asyncio.Lock] = {}
viewer_last_response: dict[str, float] = {}
max_response_per_minute = 30
runtime_tasks: set[asyncio.Task] = set()


def viewer_lock(username: str) -> asyncio.Lock:
    key = (username or 'viewer').strip().lower()
    lock = viewer_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        viewer_locks[key] = lock
    return lock


def schedule_runtime_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    runtime_tasks.add(task)
    task.add_done_callback(runtime_tasks.discard)
    return task


def normalize_channel_name(channel: str) -> str:
    if not channel:
        return ''
    return channel.strip().strip('#').lower().strip()


DEFAULT_RESPONSE_TRIGGERS = ('Зетка', 'Зеточка', 'НейроЗетка', 'neyrozetka', 'Зет')


def get_response_triggers() -> tuple[str, ...]:
    with SessionLocal() as db:
        persona = db.query(PersonaSettings).first()
        raw = persona.response_triggers if persona else ''
    try:
        configured = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        configured = []
    if not isinstance(configured, list):
        configured = []
    triggers = tuple(dict.fromkeys([*DEFAULT_RESPONSE_TRIGGERS, *(str(item).strip() for item in configured if str(item).strip())]))
    return triggers


async def safe_background_task(task_name: str, coro, *, channel_name: str | None = None) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception('Background task failed: %s', task_name)
        if channel_name:
            message = f"Не удалось подключиться к каналу '{channel_name}'. Убедитесь, что логин канала указан без ошибок и OAuth-токен активен."
        elif 'gemini' in task_name.lower():
            message = f'Gemini временно недоступен: {exc}'
        else:
            message = f'Фоновая задача "{task_name}" завершилась с ошибкой: {exc}'
        await publish_notification('error', message, retry_action=task_name)


async def publish_notification(level: str, message: str, *, retry_action: str = '') -> None:
    with SessionLocal.begin() as db:
        db.add(Log(log_type=f'notification:{level}', text=message))
    await hub.broadcast({'type': 'NOTIFICATION', 'level': level, 'message': message, 'retry_action': retry_action})


def refresh_gemini_runtime() -> None:
    global gemini_service
    gemini_service.settings = settings
    gemini_service._client = None
    if not settings.gemini_api_key:
        return
    try:
        from google import genai
        gemini_service._client = genai.Client(api_key=settings.gemini_api_key)
    except Exception:
        gemini_service._client = None


def hydrate_runtime_credentials() -> None:
    with SessionLocal() as db:
        persona = db.query(PersonaSettings).first()
        if persona:
            for provider in ('gemini', 'deepseek', 'openai', 'groq'):
                encrypted_key = getattr(persona, f'{provider}_key_encrypted', '')
                if not encrypted_key:
                    continue
                try:
                    value = decrypt(encrypted_key, settings.local_encryption_key)
                except ValueError:
                    continue
                if value:
                    setattr(settings, f'{provider}_api_key', value)

            if persona.jeetbot_api_key_encrypted:
                try:
                    jeetbot_service.api_key = decrypt(persona.jeetbot_api_key_encrypted, settings.local_encryption_key)
                except ValueError:
                    jeetbot_service.api_key = ''

            configured_model = (persona.gemini_model or settings.gemini_model).strip()
            settings.gemini_model = configured_model or settings.gemini_model
            configured_groq_model = (persona.groq_model or settings.groq_model).strip().strip('"\'').strip()
            if configured_groq_model in {'llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'llama-3.1-70b-versatile'}:
                configured_groq_model = 'openai/gpt-oss-20b'
                persona.groq_model = configured_groq_model
                db.commit()
            settings.groq_model = configured_groq_model or 'openai/gpt-oss-20b'
            settings.jeetbot_webhook_url = (persona.jeetbot_webhook_url or persona.jeetbot_endpoint or settings.jeetbot_webhook_url).strip()
            settings.jeetbot_api_key = ''
            for field in ('elevenlabs_api_key', 'youtube_token', 'obs_password'):
                encrypted_column = {
                    'elevenlabs_api_key': 'elevenlabs_key_encrypted',
                    'youtube_token': 'youtube_token_encrypted',
                    'obs_password': 'obs_password_encrypted',
                }[field]
                encrypted_key = getattr(persona, encrypted_column, '')
                if encrypted_key:
                    try:
                        setattr(settings, field, decrypt(encrypted_key, settings.local_encryption_key))
                    except ValueError:
                        setattr(settings, field, '')
            settings.youtube_channel = persona.youtube_channel or settings.youtube_channel
            settings.obs_url = persona.obs_url or settings.obs_url
            settings.obs_enabled = bool(persona.obs_enabled)
            settings.obs_capture_interval = persona.obs_capture_interval or settings.obs_capture_interval
            if persona.jeetbot_api_key_encrypted:
                try:
                    settings.jeetbot_api_key = decrypt(persona.jeetbot_api_key_encrypted, settings.local_encryption_key)
                except ValueError:
                    settings.jeetbot_api_key = ''

        broadcaster = db.query(Account).filter(Account.account_type == 'broadcaster').first()
        bot = db.query(Account).filter(Account.account_type == 'bot').first()
        settings.twitch_bot_username = ''
        settings.twitch_bot_token = ''
        twitch_service.bot_username = ''

        stale_bots = {'qa_bot', 'neyrozetka', 'sentinel_bot', 'bot-client-123'}
        if bot and not bot.connected and (bot.username or '').strip().casefold() in stale_bots:
            bot.username = ''
            bot.connected = False
            bot.token_encrypted = ''
            bot.client_id = ''
            settings.twitch_bot_username = ''
            settings.twitch_bot_token = ''
            settings.twitch_channel = ''
        if (persona and (persona.llm_provider or '').strip().casefold() != 'groq'):
            persona.llm_provider = 'groq'
            db.commit()
        else:
            db.commit()

        if broadcaster:
            settings.twitch_channel = normalize_channel_name(broadcaster.username or settings.twitch_channel)
            if broadcaster.token_encrypted:
                try:
                    settings.twitch_broadcaster_token = decrypt(broadcaster.token_encrypted, settings.local_encryption_key)
                except ValueError:
                    settings.twitch_broadcaster_token = ''
        if bot and bot.username:
            settings.twitch_bot_username = bot.username.strip()
            if bot.token_encrypted:
                try:
                    settings.twitch_bot_token = decrypt(bot.token_encrypted, settings.local_encryption_key)
                except ValueError:
                    settings.twitch_bot_token = ''

    refresh_gemini_runtime()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    if settings.twitch_bot_token and settings.twitch_channel:
        twitch_service.configure(settings.twitch_bot_token, normalize_channel_name(settings.twitch_channel), settings.twitch_bot_username)
    obs_service.configure(settings.obs_url, settings.obs_password, settings.obs_enabled)


async def ensure_twitch_connect_with_retry(max_attempts: int = 6, base_delay: float = 1.0) -> None:
    if not settings.twitch_bot_token or not settings.twitch_channel:
        return
    channel_name = normalize_channel_name(settings.twitch_channel)
    if not channel_name:
        return
    delay = base_delay
    for attempt in range(1, max_attempts + 1):
        try:
            if not twitch_service.client:
                twitch_service.configure(settings.twitch_bot_token, channel_name, settings.twitch_bot_username)
            return
        except Exception:
            pass
        if attempt < max_attempts:
            await asyncio.sleep(delay)
            delay *= 2


async def ensure_twitch_reconnect_loop() -> None:
    global irc_task
    last_token_check = 0.0
    while True:
        try:
            now = asyncio.get_running_loop().time()
            if now - last_token_check >= 60:
                await verify_saved_bot_token()
                last_token_check = now
            # twitchio.start() intentionally stays alive for the whole IRC session.
            # A long-running task is healthy when Twitch has marked it ready; only
            # restart a task that is still connecting and has genuinely stalled.
            task_stalled = (
                irc_task is not None
                and not irc_task.done()
                and not twitch_service.connected
                and now - irc_started_at > 45
            )
            with SessionLocal() as db:
                bot_account = db.query(Account).filter(Account.account_type == 'bot').first()
                bot_verified = bool(bot_account and bot_account.connected)
            if settings.twitch_bot_token and settings.twitch_channel and bot_verified and not twitch_service.join_blocked and not twitch_service.connected and (irc_task is None or irc_task.done() or task_stalled):
                channel_name = normalize_channel_name(settings.twitch_channel)
                await start_twitch_session(channel_name, 'irc_reconnect')
            if twitch_service.connected:
                await retry_pending_queue()
        except Exception as exc:
            message = str(exc)
            if 'Invalid or unauthorized Access Token passed' in message or 'AuthenticationError' in message:
                logger.warning('Twitch OAuth token is invalid or expired; stopping reconnect loop until credentials are refreshed.')
                break
            logger.exception('Twitch reconnect loop failed')
        await asyncio.sleep(20)


async def retry_pending_queue() -> None:
    with SessionLocal() as db:
        item = db.query(QueueItem).filter(QueueItem.status == 'pending').order_by(QueueItem.created_at.asc()).first()
        if not item:
            return
        item_id = item.id
    await queue_action(item_id, 'sent')


async def verify_saved_bot_token() -> None:
    if not settings.twitch_bot_token or not settings.twitch_bot_username:
        return
    with SessionLocal() as db:
        account = db.query(Account).filter(Account.account_type == 'bot').first()
        if not account or not account.token_encrypted:
            return
        try:
            token = decrypt(account.token_encrypted, settings.local_encryption_key)
        except ValueError as error:
            token = ''
        username = account.username
        client_id = account.client_id if account and len((account.client_id or '').strip()) >= 10 and account.client_id.isalnum() else settings.twitch_client_id or DEFAULT_TWITCH_CLIENT_ID
    try:
        if not token:
            raise TwitchVerificationError('Сохранённый токен бота не удалось расшифровать')
        await verify_twitch_credentials(username, client_id, token)
    except (ValueError, TwitchVerificationError) as error:
        twitch_service.mark_disconnected()
        with SessionLocal.begin() as update_db:
            saved = update_db.query(Account).filter(Account.account_type == 'bot').first()
            if saved:
                saved.connected = False
        await hub.broadcast({'type': 'IRC_STATUS', 'connected': False, 'message': f'Токен Twitch бота требует повторной авторизации: {error}'})
        return
    if not twitch_service.connected:
        await hub.broadcast({'type': 'IRC_STATUS', 'connected': False, 'message': 'Токен бота действителен, выполняется переподключение Twitch IRC.'})


async def start_twitch_session(channel_name: str, task_name: str) -> None:
    global irc_task, irc_started_at
    async with irc_reconnect_lock:
        if irc_task is not None and not irc_task.done():
            irc_task.cancel()
            with suppress(asyncio.CancelledError):
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(irc_task, timeout=3)
        if twitch_service.client and hasattr(twitch_service.client, 'close'):
            with suppress(Exception):
                await asyncio.wait_for(twitch_service.client.close(), timeout=3)
        twitch_service.configure(settings.twitch_bot_token, channel_name, settings.twitch_bot_username)
        if twitch_service.client and hasattr(twitch_service.client, 'start'):
            async def run_client() -> None:
                try:
                    await twitch_service.client.start()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    twitch_service.mark_disconnected()
                    logger.warning('Twitch IRC task ended: %s', error)
                    await hub.broadcast({'type': 'IRC_STATUS', 'connected': False, 'message': f'[IRC] Connection ended: {error}'})
                else:
                    twitch_service.mark_disconnected()
                    await hub.broadcast({'type': 'IRC_STATUS', 'connected': False, 'message': '[IRC] Connection ended; reconnecting'})
            irc_task = asyncio.create_task(run_client(), name=task_name)
            irc_started_at = asyncio.get_running_loop().time()


class ConnectionHub:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def add(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def remove(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        disconnected = []
        for connection in self.connections:
            try:
                await connection.send_json(payload)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.remove(connection)


hub = ConnectionHub()


class EventRequest(BaseModel):
    event: str = Field(pattern='^(died|victory|silence)$')


class MemoryRequest(BaseModel):
    type: str = Field(min_length=1, max_length=20)
    value: str = Field(min_length=1, max_length=500)


class AccountRequest(BaseModel):
    account_type: str = Field(pattern='^(broadcaster|bot)$')
    username: str = Field(min_length=1, max_length=100)
    client_id: str = ''
    token: str = Field(min_length=1, max_length=500)


class QueueAction(BaseModel):
    response: str | None = None


class SettingsRequest(BaseModel):
    # PATCH-like semantics prevent a request containing only one setting/key
    # from replacing all omitted values with schema defaults.
    bot_name: str | None = None
    system_prompt: str | None = None
    response_triggers: list[str] | None = None
    temperature: float | None = None
    cooldown: float | None = None
    attention_threshold: int | None = None
    jeetbot_endpoint: str | None = None
    jeetbot_webhook_url: str | None = None
    jeetbot_api_key: str | None = None
    voice_id: str | None = None
    speed: float | None = None
    pitch: float | None = None
    tos_guard: bool | None = None
    auto_reply: bool | None = None
    llm_provider: str | None = None
    avatar_idle: str | None = None
    avatar_talking: str | None = None
    avatar_rage: str | None = None
    avatar_hype: str | None = None
    gemini_model: str | None = None
    gemini_api_key: str | None = None
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    groq_model: str | None = None
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    tts_provider: str | None = None
    youtube_channel: str | None = None
    youtube_token: str | None = None
    obs_url: str | None = None
    obs_password: str | None = None
    obs_enabled: bool | None = None
    obs_capture_interval: float | None = Field(default=None, ge=1, le=300)
    twitch_channel: str | None = None
    twitch_bot_username: str | None = None
    twitch_broadcaster_client_id: str | None = None
    twitch_bot_client_id: str | None = None
    twitch_broadcaster_token: str | None = None
    twitch_bot_token: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global irc_task
    init_db()
    hydrate_runtime_credentials()
    obs_service.configure(settings.obs_url, settings.obs_password, settings.obs_enabled)
    if settings.obs_enabled:
        await obs_service.connect()
    twitch_service.on_message = process_chat_message
    await ensure_twitch_connect_with_retry()
    reconnect_task = asyncio.create_task(ensure_twitch_reconnect_loop())
    with SessionLocal() as db:
        bot_account = db.query(Account).filter(Account.account_type == 'bot').first()
        bot_verified = bool(bot_account and bot_account.connected)
    if twitch_service.client and bot_verified and hasattr(twitch_service.client, 'start'):
        await start_twitch_session(normalize_channel_name(settings.twitch_channel), 'irc_startup')
    obs_task = asyncio.create_task(obs_capture_loop())
    await obs_service.connect()
    yield
    for background_task in (obs_task, reconnect_task, *runtime_tasks):
        background_task.cancel()
    with suppress(asyncio.TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(obs_task, reconnect_task, *runtime_tasks, return_exceptions=True),
            timeout=5,
        )
    runtime_tasks.clear()
    if irc_task and twitch_service.client and hasattr(twitch_service.client, 'close'):
        irc_task.cancel()
        try:
            await twitch_service.client.close()
        except Exception:
            pass
    if irc_task and not irc_task.done():
        irc_task.cancel()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.gather(irc_task, return_exceptions=True), timeout=5)
    twitch_http = getattr(getattr(twitch_service, 'client', None), '_http', None)
    twitch_session = getattr(twitch_http, 'session', None)
    if twitch_session and not twitch_session.closed:
        await twitch_session.close()
    await obs_service.disconnect()


app = FastAPI(title=settings.app_name, version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
UPLOAD_DIR = Path(__file__).resolve().parents[1] / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')


def state_payload() -> dict:
    with SessionLocal() as db:
        mood = db.query(Mood).first()
        memories = db.query(Memory).all()
        queue = db.query(QueueItem).filter(QueueItem.status == 'pending').all()
        persona = db.query(PersonaSettings).first()
        accounts = db.query(Account).all()
        active_account = next((account for account in accounts if account.account_type == 'broadcaster'), None)
        try:
            response_triggers = json.loads(persona.response_triggers or '[]')
        except (TypeError, json.JSONDecodeError):
            response_triggers = list(DEFAULT_RESPONSE_TRIGGERS)
        return {'type': 'state', 'timestamp': datetime.now(timezone.utc).isoformat(), 'mood': {'hype': mood.hype, 'sarcasm': mood.sarcasm, 'empathy': mood.empathy, 'label': mood.label}, 'memory': {'short_term': [], 'long_term': [{'id': item.id, 'type': item.memory_type, 'value': item.value} for item in memories]}, 'queue': [{'id': item.id, 'user': item.user, 'message': item.message, 'response': item.response, 'confidence': item.confidence, 'time': item.created_at.isoformat() if item.created_at else ''} for item in queue], 'settings': {'bot_name': persona.bot_name, 'system_prompt': persona.system_prompt, 'temperature': persona.temperature, 'cooldown': persona.cooldown, 'attention_threshold': persona.attention_threshold, 'jeetbot_endpoint': persona.jeetbot_endpoint, 'jeetbot_webhook_url': persona.jeetbot_webhook_url or persona.jeetbot_endpoint, 'voice_id': persona.voice_id, 'speed': persona.speed, 'pitch': persona.pitch, 'tos_guard': persona.tos_guard, 'auto_reply': persona.auto_reply, 'llm_provider': persona.llm_provider, 'gemini_model': persona.gemini_model or settings.gemini_model, 'groq_model': persona.groq_model or settings.groq_model, 'elevenlabs_voice_id': persona.elevenlabs_voice_id, 'tts_provider': persona.tts_provider, 'youtube_channel': persona.youtube_channel, 'obs_url': persona.obs_url, 'obs_enabled': persona.obs_enabled, 'obs_capture_interval': persona.obs_capture_interval, 'adaptive_context': persona.adaptive_context, 'context_summary': persona.context_summary, 'response_triggers': response_triggers, 'avatar_idle': persona.avatar_idle, 'avatar_talking': persona.avatar_talking, 'avatar_rage': persona.avatar_rage, 'avatar_hype': persona.avatar_hype}, 'accounts': [{'account_type': account.account_type, 'username': account.username, 'display_name': account.display_name, 'profile_image_url': account.profile_image_url, 'connected': account.connected, 'moderator': account.moderator, 'live': account.live} for account in accounts], 'twitch': {'connected': twitch_service.connected, 'channel': active_account.username if active_account else '', 'display_name': active_account.display_name if active_account else '', 'profile_image_url': active_account.profile_image_url if active_account else '', 'live': bool(active_account and active_account.live), 'bot_user': twitch_service.bot_username, 'error': twitch_service.last_error}}


async def obs_capture_loop() -> None:
    while True:
        await asyncio.sleep(max(1, settings.obs_capture_interval))
        if not obs_service.enabled:
            continue
        try:
            image_data = await obs_service.screenshot()
            await hub.broadcast({
                'type': 'OBS_FRAME_CAPTURED',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'has_image': bool(image_data),
            })
        except Exception as error:
            obs_service.connected = False
            obs_service.last_error = str(error)
            await hub.broadcast({'type': 'OBS_STATUS', **obs_service.status()})


def process_chat_message(viewer_name: str, message: str) -> None:
    command = parse_viewer_command(message, viewer_name, get_response_triggers())
    remember_viewer_message(viewer_name, message, bool(command))
    if command:
        asyncio.create_task(hub.broadcast({'type': 'CHAT_MESSAGE_RECEIVED', 'message': {
            'user': viewer_name,
            'message': message,
            'color': '#60a5fa',
            'badge': 'MENTION',
        }}))
        asyncio.create_task(safe_background_task('handle_trigger', handle_trigger(command)))


def remember_streamer_transcript(transcript: str) -> None:
    text = (transcript or '').strip()
    if text:
        recent_streamer_transcripts.append(text[:1000])
        streamer_name = (settings.twitch_channel or 'стример').strip().lower()
        with SessionLocal.begin() as db:
            profile = db.query(StreamerProfile).filter(StreamerProfile.username == streamer_name).first()
            if not profile:
                profile = StreamerProfile(username=streamer_name)
                db.add(profile)
            profile.summary = deterministic_summary([profile.summary, text])
        lowered = text.casefold()
        if any(marker in lowered for marker in ('запомни', 'учти', 'отвечай короче', 'отвечай подробнее', 'без шуток', 'больше шуток')):
            with SessionLocal.begin() as db:
                persona = db.query(PersonaSettings).first()
                if persona:
                    entries = [entry for entry in (persona.adaptive_context or '').splitlines() if entry.strip()]
                    entries.append(f'Предпочтение стримера: {text[:500]}')
                    persona.adaptive_context = '\n'.join(entries[-20:])


def parse_streamer_command(transcript: str) -> Any:
    text = (transcript or '').strip()
    if not text:
        return None
    wake = extract_wake_word(text, WAKE_WORDS)
    if not wake:
        return None
    wake_word, prompt = wake
    if not prompt:
        return None
    return ViewerCommand(
        command=wake_word,
        viewer_name=settings.twitch_channel or 'стример',
        prompt=prompt,
        is_streamer=True,
    )


def streamer_context() -> str:
    if not recent_streamer_transcripts:
        return 'Реплик стримера пока нет.'
    return '\n'.join(f'- {text}' for text in recent_streamer_transcripts)


def remember_viewer_message(viewer_name: str, message: str, is_mention: bool) -> None:
    username = (viewer_name or 'viewer').strip().lower()[:100]
    text = sanitize_viewer_message(message)
    if not username or not text:
        return
    with SessionLocal.begin() as db:
        profile = db.query(ViewerProfile).filter(ViewerProfile.username == username).first()
        now = datetime.now(timezone.utc)
        if not profile:
            profile = ViewerProfile(username=username, message_count=1, first_seen_at=now, last_seen_at=now)
            db.add(profile)
        else:
            profile.message_count += 1
            profile.last_seen_at = now
        profile.summary = deterministic_summary([profile.summary, text])
        db.add(ViewerMessage(username=username, message=text[:2000], is_mention=is_mention))
        db.add(ChatMemory(username=username, role='viewer', content=text[:2000], is_mention=is_mention))


def viewer_context(username: str) -> str:
    normalized = (username or 'viewer').strip().lower()
    with SessionLocal() as db:
        profile = db.query(ViewerProfile).filter(ViewerProfile.username == normalized).first()
        messages = db.query(ViewerMessage).filter(ViewerMessage.username == normalized).order_by(ViewerMessage.created_at.desc()).limit(12).all()
    if not profile and not messages:
        return 'Новый зритель, личной истории пока нет.'
    history = '\n'.join(f'- {item.message}' for item in reversed(messages))
    return (
        f'Профиль зрителя @{normalized}: сообщений {profile.message_count if profile else len(messages)}. '
        f'Последняя активность: {profile.last_seen_at.isoformat() if profile else "сейчас"}.\n'
        f'Последние сообщения:\n{history}'
    )


def recent_chat_context(username: str, limit: int = 16) -> str:
    normalized = (username or 'viewer').strip().lower()
    with SessionLocal() as db:
        rows = db.query(ChatMemory).filter(
            (ChatMemory.username == normalized) | (ChatMemory.username == '')
        ).order_by(ChatMemory.created_at.desc()).limit(limit).all()
    return '\n'.join(f'- {row.role}: {row.content}' for row in reversed(rows))


async def handle_trigger(command) -> None:
    username_key = (command.viewer_name or 'viewer').strip().lower()
    lock = viewer_lock(username_key)
    if lock.locked():
        await publish_notification('warning', f'Пропущен дубликат ответа для @{command.viewer_name}')
        return
    async with lock:
        await _handle_trigger_locked(command, username_key)


async def _handle_trigger_locked(command, username_key: str) -> None:
    now = time.monotonic()
    recent_count = sum(1 for timestamp in viewer_last_response.values() if now - timestamp < 60)
    if recent_count >= max_response_per_minute:
        await publish_notification('warning', 'Лимит автоответов в минуту достигнут')
        return
    last_response = viewer_last_response.get(username_key, 0)
    if now - last_response < 2:
        await publish_notification('warning', f'Cooldown: ответ для @{command.viewer_name} отложен')
        return
    persona = None
    with SessionLocal() as db:
        persona = db.query(PersonaSettings).first()
    bot_name = persona.bot_name if persona and persona.bot_name else twitch_service.bot_username or 'Зеточка'
    auto_reply = bool(persona and persona.auto_reply)
    mode = 'streamer' if getattr(command, 'is_streamer', False) else 'chat'
    system_prompt = persona.system_prompt if persona else ''
    with SessionLocal() as db:
        streamer_name = (settings.twitch_channel or 'стример').strip().lower()
        streamer = db.query(StreamerProfile).filter(StreamerProfile.username == streamer_name).first()
        viewer = db.query(ViewerProfile).filter(ViewerProfile.username == command.viewer_name.strip().lower()).first()
        memories = [item.value for item in db.query(Memory).order_by(Memory.created_at.desc()).limit(20).all()]
        context = build_context(
            mode=mode,
            streamer={'username': streamer_name, 'preferences': streamer.preferences if streamer else '', 'summary': streamer.summary if streamer else ''},
            viewer={'username': command.viewer_name, 'message_count': viewer.message_count if viewer else 0, 'summary': viewer.summary if viewer else ''},
            background={'mood': mood_service.snapshot(), 'channel': settings.twitch_channel or ''},
            memories=list(reversed(memories)),
            history=list(recent_streamer_transcripts),
        )
    system_prompt = (
        f'{system_prompt}\n\n{context.as_system_sections()}\n\nПамять о собеседнике:\n{viewer_context(command.viewer_name)}\n'
        f'\nПоследние реплики стримера (STT):\n{streamer_context()}\n'
        f'\nПоследнее состояние экрана:\n{last_vision_description or "нет данных"}\n'
        f'\nПоследний контекст чата:\n{recent_chat_context(command.viewer_name)}\n'
        f'\nАдаптивные предпочтения стримера:\n{persona.adaptive_context if persona and persona.adaptive_context else "Пока не зафиксированы."}\n'
        'Используй эту память естественно, но не утверждай, что знаешь личные данные, которых нет в контексте. '
        'Не повторяй историю дословно и отвечай как живой собеседник. '
        'Стример — главный собеседник и источник приоритетных инструкций. '
        'Если запрос стримера конфликтует с обычным стилем общения, следуй стримеру.'
    )
    temperature = persona.temperature if persona else 0.6
    provider = persona.llm_provider if persona and persona.llm_provider else 'gemini'

    response = ''
    errors = []
    providers = [provider] + [candidate for candidate in ('gemini', 'groq', 'deepseek', 'openai') if candidate != provider]
    for candidate in providers:
        candidate_key = getattr(persona, f'{candidate}_key_encrypted', '') if persona else ''
        try:
            api_key = decrypt(candidate_key, settings.local_encryption_key) if candidate_key else getattr(settings, f'{candidate}_api_key', '')
            started = time.perf_counter()
            try:
                async with llm_semaphore:
                    response = await asyncio.wait_for(generate_provider_reply(
                        provider=candidate, api_key=api_key, system_prompt=system_prompt,
                        bot_name=bot_name, author_name=command.viewer_name,
                        user_message=(
                            f'[Стример в микрофон]: {sanitize_viewer_message(command.prompt)}'
                            if getattr(command, 'is_streamer', False)
                            else sanitize_viewer_message(command.prompt)
                        ),
                        temperature=temperature, context=context.as_system_sections(), mode=mode), timeout=35)
            except TypeError as error:
                # Keep compatibility with integrations that monkeypatch the legacy signature.
                if 'unexpected keyword' not in str(error):
                    raise
                async with llm_semaphore:
                    response = await asyncio.wait_for(generate_provider_reply(
                        provider=candidate, api_key=api_key, system_prompt=system_prompt,
                        bot_name=bot_name, author_name=command.viewer_name,
                        user_message=(
                            f'[Стример в микрофон]: {sanitize_viewer_message(command.prompt)}'
                            if getattr(command, 'is_streamer', False)
                            else sanitize_viewer_message(command.prompt)
                        ), temperature=temperature), timeout=35)
            latency = (time.perf_counter() - started) * 1000
            with SessionLocal.begin() as db:
                db.add(LlmObservation(provider=candidate, mode=mode, latency_ms=latency, success=True, reason='primary' if candidate == provider else 'fallback'))
            break
        except (LlmProviderError, ValueError, asyncio.TimeoutError) as error:
            errors.append(f'{candidate}: {error}')
            with SessionLocal.begin() as db:
                db.add(LlmObservation(provider=candidate, mode=mode, latency_ms=0, success=False, reason=str(error)[:200]))
            continue
    if not response:
        error = LlmProviderError(provider, '; '.join(errors) or 'No configured LLM provider', 502)
        await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': str(error)})
        return
    viewer_last_response[username_key] = time.monotonic()
    queue_item_id = None
    item = {'id': None, 'user': command.viewer_name, 'message': command.prompt, 'response': response, 'confidence': 95, 'time': 'now'}
    with SessionLocal.begin() as db:
        queue_item = QueueItem(user=command.viewer_name, message=command.prompt, response=response, confidence=95)
        db.add(queue_item)
        db.flush()
        queue_item_id = queue_item.id
        item = {'id': queue_item_id, 'user': queue_item.user, 'message': queue_item.message, 'response': queue_item.response, 'confidence': queue_item.confidence, 'time': 'now'}

    await hub.broadcast({'type': 'BOT_START_TALKING', 'text': response, 'viewer_name': command.viewer_name, 'prompt': command.prompt, 'avatar_state': 'talking'})
    if getattr(command, 'is_streamer', False):
        await hub.broadcast({'type': 'STREAMER_ANSWER', 'text': response, 'viewer_name': command.viewer_name})
        if twitch_service.connected:
            await twitch_service.send_message(response)
    elif auto_reply and queue_item_id is not None:
        try:
            await queue_action(queue_item_id, 'sent')
        except HTTPException as error:
            await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': error.detail})
    else:
        await hub.broadcast({'type': 'VIEWER_COMMAND_ANSWER', 'command': command.command, 'viewer_name': command.viewer_name, 'prompt': command.prompt, 'item': item})


@app.get('/health')
async def health() -> dict:
    with SessionLocal() as db:
        db.execute(text('SELECT 1'))
    services = {
        'api': True,
        'database': True,
        'twitch': twitch_service.connected,
        'obs': obs_service.connected if obs_service.enabled else None,
        'llm': bool(settings.gemini_api_key or settings.groq_api_key or settings.openai_api_key or settings.deepseek_api_key),
    }
    return {'status': 'ok' if services['database'] else 'degraded', 'environment': settings.environment, 'services': services}


@app.get('/health/live')
async def health_live() -> dict:
    return {'status': 'ok'}


@app.get('/health/ready')
async def health_ready() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text('SELECT 1'))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f'Database is not ready: {error}') from error
    return {'status': 'ok', 'services': {'api': True, 'database': True}}


@app.get('/api/notifications')
async def get_notifications(limit: int = 50) -> list[dict]:
    with SessionLocal() as db:
        rows = db.query(Log).filter(Log.log_type.like('notification:%')).order_by(Log.created_at.desc()).limit(max(1, min(limit, 200))).all()
        return [{'id': row.id, 'level': row.log_type.split(':', 1)[-1], 'message': row.text, 'created_at': row.created_at.isoformat()} for row in rows]


@app.get('/api/observability/llm')
async def llm_observability() -> dict:
    """Small, non-sensitive latency/provider view for the dashboard and operators."""
    with SessionLocal() as db:
        rows = db.query(LlmObservation).order_by(LlmObservation.created_at.desc()).limit(100).all()
    return {'items': [
        {'provider': row.provider, 'mode': row.mode, 'latency_ms': round(row.latency_ms, 1),
         'success': row.success, 'reason': row.reason, 'created_at': row.created_at.isoformat()}
        for row in rows
    ]}


@app.get('/api/metrics')
async def metrics() -> dict:
    with SessionLocal() as db:
        total = db.query(LlmObservation).count()
        failures = db.query(LlmObservation).filter(LlmObservation.success.is_(False)).count()
        fallback = db.query(LlmObservation).filter(LlmObservation.reason == 'fallback').count()
        notifications = db.query(Log).filter(Log.log_type.like('notification:%')).count()
    return {'llm_calls': total, 'llm_failures': failures, 'fallback_calls': fallback, 'notifications': notifications, 'twitch_connected': twitch_service.connected, 'obs_connected': obs_service.connected}


@app.get('/api/obs/status')
async def obs_status() -> dict:
    return obs_service.status()


@app.post('/api/obs/reconnect')
async def obs_reconnect() -> dict:
    await obs_service.disconnect()
    await obs_service.connect()
    payload = obs_service.status()
    await hub.broadcast({'type': 'OBS_STATUS', **payload})
    return payload


class ObsScreenshotRequest(BaseModel):
    source: str = ''


@app.post('/api/obs/screenshot')
async def obs_screenshot(request: ObsScreenshotRequest) -> dict:
    try:
        image_data = await obs_service.screenshot(request.source)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {'image_data': image_data, 'source': request.source}


@app.get('/api/memory/chat')
async def get_chat_memory(username: str = '', limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 500))
    with SessionLocal() as db:
        query = db.query(ChatMemory)
        if username.strip():
            query = query.filter(ChatMemory.username == username.strip().lower())
        rows = query.order_by(ChatMemory.created_at.desc()).limit(limit).all()
        return [{'id': row.id, 'username': row.username, 'role': row.role, 'content': row.content, 'is_mention': row.is_mention, 'created_at': row.created_at.isoformat()} for row in rows]


@app.delete('/api/memory/chat')
async def clear_chat_memory(username: str = '') -> dict:
    with SessionLocal.begin() as db:
        query = db.query(ChatMemory)
        if username.strip():
            query = query.filter(ChatMemory.username == username.strip().lower())
        deleted = query.delete()
    return {'deleted': deleted}


@app.get('/v1/models')
async def list_llm_models() -> dict:
    provider = 'gemini'
    with SessionLocal() as db:
        persona = db.query(PersonaSettings).first()
        if persona and persona.llm_provider:
            provider = persona.llm_provider.lower()

    model_choices = {
        'gemini': ['gemini-3.6-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash'],
        'deepseek': ['deepseek-chat', 'deepseek-reasoner'],
        'openai': ['gpt-4o-mini', 'gpt-4o'],
        'groq': ['openai/gpt-oss-20b', 'llama-3.1-8b-instant'],
    }
    selected = model_choices.get(provider, ['gemini-2.0-flash'])
    if provider == 'gemini' and settings.gemini_model:
        selected = [settings.gemini_model, *[model for model in selected if model != settings.gemini_model]]

    seen = set()
    ordered = []
    for model in selected:
        normalized = (model or '').strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    if 'gemini-3.6-flash' not in seen:
        ordered.append('gemini-3.6-flash')

    return {'object': 'list', 'data': [{'id': model, 'object': 'model', 'created': 0, 'owned_by': 'system'} for model in ordered]}


@app.get('/api/state')
async def get_state() -> dict:
    return state_payload()


@app.post('/api/mood/event')
async def mood_event(request: EventRequest) -> dict:
    mood = mood_service.apply_event(request.event)
    with SessionLocal.begin() as db:
        record = db.query(Mood).first()
        record.hype, record.sarcasm, record.empathy, record.label = mood['hype'], mood['sarcasm'], mood['empathy'], mood['label']
        db.add(Log(log_type='reasoning', text=f'Mood event: {request.event}'))
    await hub.broadcast({'type': 'mood', 'mood': mood})
    return mood


@app.get('/api/memory')
async def get_memory() -> dict:
    with SessionLocal() as db:
        return {'short_term': [], 'long_term': [{'id': item.id, 'type': item.memory_type, 'value': item.value} for item in db.query(Memory).all()]}


@app.post('/api/memory')
async def add_memory(request: MemoryRequest) -> dict:
    with SessionLocal.begin() as db:
        item = Memory(memory_type=request.type.upper(), value=request.value)
        db.add(item)
        db.flush()
        result = {'id': item.id, 'type': item.memory_type, 'value': item.value}
    await hub.broadcast({'type': 'memory', 'memory': memory_service.snapshot()})
    return result


@app.delete('/api/memory/{item_id}')
async def delete_memory(item_id: int) -> dict:
    with SessionLocal.begin() as db:
        item = db.get(Memory, item_id)
        if not item:
            raise HTTPException(status_code=404, detail='Memory item not found')
        db.delete(item)
    await hub.broadcast({'type': 'memory', 'memory': memory_service.snapshot()})
    return {'deleted': item_id}


@app.post('/api/memory/reset')
async def reset_memory() -> dict:
    with SessionLocal.begin() as db:
        db.query(Memory).delete()
    await hub.broadcast({'type': 'memory', 'memory': memory_service.snapshot()})
    return {'short_term': [], 'long_term': []}


@app.get('/api/accounts')
async def get_accounts() -> list[dict]:
    with SessionLocal() as db:
        return [{'account_type': item.account_type, 'username': item.username, 'connected': item.connected, 'moderator': item.moderator} for item in db.query(Account).all()]


@app.get('/api/twitch/status')
async def twitch_status() -> dict:
    from app.services.twitch_verify_service import fetch_stream_status
    with SessionLocal() as db:
        account = db.query(Account).filter(Account.account_type == 'broadcaster', Account.connected.is_(True)).first()
        bot = db.query(Account).filter(Account.account_type == 'bot', Account.connected.is_(True)).first()
        if not account:
            return {'connected': False, 'live': False, 'channel': '', 'bot_user': bot.username if bot else ''}
        try:
            live = await fetch_stream_status(account.username, account.client_id, decrypt(account.token_encrypted, settings.local_encryption_key))
        except Exception:
            live = False
        account.live = live
        db.commit()
        return {'connected': twitch_service.connected, 'live': live, 'channel': account.username, 'bot_user': bot.username if bot else twitch_service.bot_username, 'display_name': account.display_name, 'profile_image_url': account.profile_image_url}


@app.post('/api/twitch/verify')
async def verify_account(request: AccountRequest) -> dict:
    requested_client_id = request.client_id.strip()
    client_id = requested_client_id if requested_client_id and len(requested_client_id) >= 10 and requested_client_id.isalnum() else ''
    client_id = client_id or settings.twitch_client_id.strip() or DEFAULT_TWITCH_CLIENT_ID
    if not client_id:
        with SessionLocal() as db:
            broadcaster = db.query(Account).filter(Account.account_type == 'broadcaster').first()
            client_id = (broadcaster.client_id if broadcaster else '').strip()
    if not client_id:
        raise HTTPException(status_code=503, detail='Twitch OAuth application is not configured on the server')
    try:
        result = await verify_twitch_credentials(request.username, client_id, request.token)
    except TwitchVerificationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    with SessionLocal.begin() as db:
        account = db.query(Account).filter(Account.account_type == request.account_type).first()
        if not account:
            account = Account(account_type=request.account_type)
            db.add(account)
        account.username = request.username
        account.client_id = client_id
        account.token_encrypted = encrypt(request.token, settings.local_encryption_key)
        account.connected = True
        account.moderator = request.account_type == 'bot'
    return {'valid': True, 'account_type': request.account_type, 'username': result['display_name'], 'scopes': result['scopes']}


@app.get('/api/settings')
async def get_settings_api() -> dict:
    with SessionLocal() as db:
        item = db.query(PersonaSettings).first()
        if not item:
            return {}
        data = {key: getattr(item, key) for key in ('bot_name', 'system_prompt', 'temperature', 'cooldown', 'attention_threshold', 'jeetbot_endpoint', 'jeetbot_webhook_url', 'voice_id', 'speed', 'pitch', 'tos_guard', 'auto_reply', 'llm_provider', 'avatar_idle', 'avatar_talking', 'avatar_rage', 'avatar_hype', 'gemini_model', 'groq_model', 'elevenlabs_voice_id', 'tts_provider', 'youtube_channel', 'obs_url', 'obs_enabled', 'obs_capture_interval')}
        try:
            data['response_triggers'] = json.loads(item.response_triggers or '[]')
        except json.JSONDecodeError:
            data['response_triggers'] = list(DEFAULT_RESPONSE_TRIGGERS)
        data['gemini_api_key'] = settings.gemini_api_key
        data['deepseek_api_key'] = settings.deepseek_api_key
        data['openai_api_key'] = settings.openai_api_key
        data['groq_api_key'] = settings.groq_api_key
        data['elevenlabs_api_key'] = settings.elevenlabs_api_key
        data['twitch_channel'] = normalize_channel_name(settings.twitch_channel)
        data['twitch_bot_username'] = settings.twitch_bot_username
        broadcaster = db.query(Account).filter(Account.account_type == 'broadcaster').first()
        bot = db.query(Account).filter(Account.account_type == 'bot').first()
        data['twitch_broadcaster_client_id'] = broadcaster.client_id if broadcaster else ''
        data['twitch_bot_client_id'] = bot.client_id if bot else ''
        return data


@app.put('/api/settings')
async def update_settings(request: SettingsRequest) -> dict:
    values = request.model_dump(exclude_unset=True)
    with SessionLocal.begin() as db:
        item = db.query(PersonaSettings).first()
        if not item:
            item = PersonaSettings()
            db.add(item)
        secret_columns = {'gemini_api_key': 'gemini_key_encrypted', 'deepseek_api_key': 'deepseek_key_encrypted', 'openai_api_key': 'openai_key_encrypted', 'groq_api_key': 'groq_key_encrypted', 'jeetbot_api_key': 'jeetbot_api_key_encrypted', 'elevenlabs_api_key': 'elevenlabs_key_encrypted', 'youtube_token': 'youtube_token_encrypted', 'obs_password': 'obs_password_encrypted'}
        account_secret_keys = {'twitch_broadcaster_token', 'twitch_bot_token'}
        for key, column in secret_columns.items():
            secret = (values.get(key) or '').strip()
            if secret:
                setattr(item, column, encrypt(secret, settings.local_encryption_key))

        for key, value in values.items():
            if key in secret_columns or key in account_secret_keys:
                continue
            if value is None:
                continue
            if key == 'llm_provider':
                value = str(value).strip().lower()
                if value not in {'gemini', 'groq', 'deepseek', 'openai'}:
                    raise HTTPException(status_code=400, detail='Unsupported LLM provider')
            if key == 'response_triggers':
                configured = [str(trigger).strip() for trigger in (value or []) if str(trigger).strip()]
                triggers = list(dict.fromkeys([*DEFAULT_RESPONSE_TRIGGERS, *configured]))
                value = json.dumps(triggers, ensure_ascii=False)
            if key == 'jeetbot_webhook_url' and not value:
                value = values.get('jeetbot_endpoint', '')
            if key == 'twitch_channel' and value:
                normalized = normalize_channel_name(value)
                value = normalized
            elif key == 'twitch_bot_username' and value:
                value = value.strip()
            elif key == 'gemini_model' and value:
                value = value.strip()
            elif key == 'groq_model' and value:
                value = value.strip().strip('"\'').strip()
                if value in {'llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'llama-3.1-70b-versatile'}:
                    value = 'openai/gpt-oss-20b'
            elif key == 'jeetbot_webhook_url' and value:
                value = value.strip()
            setattr(item, key, value)

        if values.get('jeetbot_webhook_url'):
            item.jeetbot_webhook_url = values['jeetbot_webhook_url'].strip()
        if values.get('jeetbot_endpoint'):
            item.jeetbot_endpoint = values['jeetbot_endpoint']
        if any(values.get(key) for key in ('twitch_channel', 'twitch_bot_username', 'twitch_broadcaster_client_id', 'twitch_bot_client_id', 'twitch_broadcaster_token', 'twitch_bot_token')):
            broadcaster = db.query(Account).filter(Account.account_type == 'broadcaster').first()
            if not broadcaster:
                broadcaster = Account(account_type='broadcaster')
                db.add(broadcaster)
            if values.get('twitch_channel'):
                broadcaster.username = normalize_channel_name(values['twitch_channel'])
            if values.get('twitch_broadcaster_client_id'):
                broadcaster.client_id = str(values['twitch_broadcaster_client_id']).strip()
            if values.get('twitch_broadcaster_token'):
                broadcaster.token_encrypted = encrypt(str(values['twitch_broadcaster_token']).strip(), settings.local_encryption_key)
            bot_account = db.query(Account).filter(Account.account_type == 'bot').first()
            if not bot_account:
                bot_account = Account(account_type='bot')
                db.add(bot_account)
            if values.get('twitch_bot_username'):
                bot_account.username = str(values['twitch_bot_username']).strip()
            if values.get('twitch_bot_client_id'):
                bot_account.client_id = str(values['twitch_bot_client_id']).strip()
            if values.get('twitch_bot_token'):
                bot_account.token_encrypted = encrypt(str(values['twitch_bot_token']).strip(), settings.local_encryption_key)

        db.add(Log(log_type='action', text='Persona settings saved'))

    hydrate_runtime_credentials()
    if any(key in values for key in ('twitch_channel', 'twitch_bot_username', 'twitch_broadcaster_client_id', 'twitch_bot_client_id', 'twitch_bot_token')):
        with SessionLocal() as db:
            bot_account = db.query(Account).filter(Account.account_type == 'bot').first()
            bot_verified = bool(bot_account and bot_account.connected)
        if settings.twitch_bot_token and settings.twitch_channel and bot_verified:
            schedule_runtime_task(safe_background_task(
                'irc_settings_update',
                start_twitch_session(normalize_channel_name(settings.twitch_channel), 'irc_settings_update'),
            ))
        else:
            twitch_service.mark_disconnected()
            if irc_task and not irc_task.done():
                irc_task.cancel()
    await hub.broadcast({'type': 'settings', 'settings': values})
    return values


@app.post('/api/settings/avatar/{avatar_state}')
async def upload_avatar(avatar_state: str, file: UploadFile = File(...)) -> dict:
    if avatar_state not in {'idle', 'talking', 'rage', 'hype'}:
        raise HTTPException(status_code=400, detail='Unsupported avatar state')
    if file.content_type not in {'image/png', 'image/gif', 'image/jpeg', 'image/webp'}:
        raise HTTPException(status_code=415, detail='Only PNG, GIF, JPEG, and WebP avatars are supported')
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Avatar must be smaller than 8 MB')
    upload_dir = Path(__file__).resolve().parents[1] / 'uploads'
    upload_dir.mkdir(exist_ok=True)
    suffix = Path(file.filename or 'avatar.png').suffix.lower() or '.png'
    target = upload_dir / f'avatar_{avatar_state}{suffix}'
    target.write_bytes(content)
    public_path = f'/uploads/{target.name}'
    with SessionLocal.begin() as db:
        item = db.query(PersonaSettings).first()
        setattr(item, f'avatar_{avatar_state}', public_path)
    await hub.broadcast({'type': 'AVATAR_UPDATED', 'avatar_state': avatar_state, 'path': public_path})
    return {'avatar_state': avatar_state, 'path': public_path}


@app.post('/api/settings/meme')
async def upload_meme(file: UploadFile = File(...), sound: UploadFile | None = File(default=None)) -> dict:
    allowed_image = {'image/png', 'image/gif', 'image/jpeg', 'image/webp'}
    allowed_sound = {'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/wave'}
    if file.content_type not in allowed_image:
        raise HTTPException(status_code=415, detail='Meme must be PNG, GIF, JPEG, or WebP')
    upload_dir = Path(__file__).resolve().parents[1] / 'uploads'
    image_target = upload_dir / f'meme_{int(datetime.now().timestamp() * 1000)}{Path(file.filename or "meme.png").suffix.lower()}'
    image_target.write_bytes(await file.read())
    sound_path = ''
    if sound:
        if sound.content_type not in allowed_sound:
            raise HTTPException(status_code=415, detail='Sound must be MP3 or WAV')
        sound_target = upload_dir / f'sound_{int(datetime.now().timestamp() * 1000)}{Path(sound.filename or "sound.mp3").suffix.lower()}'
        sound_target.write_bytes(await sound.read())
        sound_path = f'/uploads/{sound_target.name}'
    return {'image_url': f'/uploads/{image_target.name}', 'sound_url': sound_path}


class SpeakingRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    avatar_state: str = 'talking'
    tts_url: str = ''


class TwitchCallbackRequest(BaseModel):
    account_type: str = Field(pattern='^(broadcaster|bot)$')
    token: str
    client_id: str
    user: dict


class MemeRequest(BaseModel):
    image_url: str
    sound_url: str = ''
    duration: int = Field(default=5000, ge=500, le=30000)


class LlmVerifyRequest(BaseModel):
    provider: str = Field(pattern='^(gemini|deepseek|openai|groq)$')
    api_key: str = Field(min_length=1)


class SandboxMessageRequest(BaseModel):
    viewer_name: str = 'sandbox_viewer'
    message: str = Field(min_length=1, max_length=500)


class IrcConnectRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=100)
    bot_username: str = Field(min_length=1, max_length=100)
    bot_token: str = Field(min_length=1, max_length=500)


class SttRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    language: str = 'ru-RU'


class NotificationTestRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class VisionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    confidence: int = Field(default=0, ge=0, le=100)


class VisionEventRequest(BaseModel):
    event: str = Field(pattern='^(death|victory|scene_change|meme|screen_change)$')
    source: str = ''


@app.post('/api/overlay/speak')
async def overlay_speak(request: SpeakingRequest) -> dict:
    payload = {'type': 'BOT_START_TALKING', 'text': request.text, 'avatar_state': request.avatar_state, 'tts_url': request.tts_url}
    await hub.broadcast(payload)
    return payload


@app.post('/api/overlay/stop')
async def overlay_stop() -> dict:
    payload = {'type': 'BOT_STOP_TALKING'}
    await hub.broadcast(payload)
    return payload


@app.post('/api/llm/verify')
async def verify_llm(request: LlmVerifyRequest) -> dict:
    api_key = request.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail='API key must not be blank')
    try:
        result = await verify_provider_key(request.provider, api_key)
        provider = request.provider.lower()
        if result.get('valid'):
            with SessionLocal.begin() as db:
                item = db.query(PersonaSettings).first()
                if not item:
                    item = PersonaSettings()
                    db.add(item)
                encrypted_column = {'gemini': 'gemini_key_encrypted', 'deepseek': 'deepseek_key_encrypted', 'openai': 'openai_key_encrypted', 'groq': 'groq_key_encrypted'}[provider]
                setattr(item, encrypted_column, encrypt(api_key, settings.local_encryption_key))
            # Update runtime only after the transaction has committed. A failed
            # commit must not make an unsaved key appear active.
            setattr(settings, f'{provider}_api_key', api_key)
            refresh_gemini_runtime()
        return result
    except (LlmProviderError, GeminiVerificationError) as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=504, detail='Temporary network timeout while verifying the API key. Please try again.') from error


@app.post('/api/sandbox/message')
async def sandbox_message(request: SandboxMessageRequest) -> dict:
    process_chat_message(request.viewer_name, request.message)
    if parse_viewer_command(request.message, request.viewer_name, get_response_triggers()):
        await hub.broadcast({'type': 'CHAT_MESSAGE_RECEIVED', 'message': {'user': request.viewer_name, 'message': request.message, 'color': '#00f5d4', 'badge': 'TEST'}})
    return {'accepted': True, 'sandbox': True}


@app.post('/api/stream/stt')
async def ingest_stt(request: SttRequest) -> dict:
    remember_streamer_transcript(request.transcript)
    await hub.broadcast({'type': 'STT_TRANSCRIPT', 'transcript': request.transcript, 'language': request.language})
    command = parse_streamer_command(request.transcript)
    if command:
        asyncio.create_task(safe_background_task('stt_trigger', handle_trigger(command)))
        await hub.broadcast({'type': 'WAKE_WORD_DETECTED', 'wake_word': command.command, 'transcript': request.transcript})
    else:
        await hub.broadcast({'type': 'WAKE_WORD_IGNORED', 'transcript': request.transcript})
    return {'accepted': True, 'triggered': bool(command), 'wake_word': command.command if command else None}


@app.post('/api/stream/stt/audio')
async def transcribe_stt_audio(file: UploadFile = File(...), language: str = 'ru') -> dict:
    audio = await file.read()
    if not audio or len(audio) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Audio is empty or larger than 15 MB')
    try:
        transcript = await asyncio.wait_for(speech_service.transcribe(audio, language), timeout=60)
    except asyncio.TimeoutError as error:
        raise HTTPException(status_code=504, detail='Speech recognition timed out') from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if transcript:
        return await ingest_stt(SttRequest(transcript=transcript, language=language))
    return {'accepted': True, 'triggered': False, 'wake_word': None, 'transcript': ''}


@app.post('/api/notifications/test')
async def send_test_notification(request: NotificationTestRequest) -> dict:
    try:
        dispatch = await twitch_service.send_message(request.message)
        if dispatch.get('sent'):
            message = 'Тестовое сообщение отправлено в чат'
            await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': message})
            return {'status': 'ok', 'message': message, 'details': dispatch}
        reason = 'Не удалось отправить тестовое сообщение: Twitch IRC не подключён или OAuth-токен неактивен.'
        if dispatch.get('mode') == 'channel-not-joined':
            reason = "Не удалось отправить тестовое сообщение: канал не найден или не подключён."
        await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': reason})
        return {'status': 'error', 'message': reason, 'details': dispatch}
    except Exception as exc:
        reason = f'Не удалось отправить тестовое сообщение: {exc}'
        await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': reason})
        return {'status': 'error', 'message': reason, 'details': {'error': str(exc)}}


@app.post('/api/stream/vision')
async def ingest_vision(request: VisionRequest) -> dict:
    global last_vision_description
    if request.description.strip() == last_vision_description.strip():
        return {'accepted': False, 'duplicate': True}
    last_vision_description = request.description.strip()
    with SessionLocal.begin() as db:
        persona = db.query(PersonaSettings).first()
        if persona:
            persona.context_summary = last_vision_description[:1800]
    await hub.broadcast({'type': 'VISION_FRAME_ANALYZED', 'description': last_vision_description, 'confidence': request.confidence})
    return {'accepted': True}


@app.post('/api/stream/vision/event')
async def vision_event(request: VisionEventRequest) -> dict:
    """Capture and analyze only meaningful stream events, not every frame."""
    image_data = await obs_service.screenshot(request.source)
    encoded = image_data.split(',', 1)[-1]
    try:
        frame = __import__('base64').b64decode(encoded)
    except Exception as error:
        raise HTTPException(status_code=502, detail='OBS returned an invalid screenshot') from error
    if not frame:
        raise HTTPException(status_code=503, detail='OBS returned an empty screenshot')
    return await ingest_vision_frame(UploadFile(filename=f'{request.event}.jpg', file=__import__('io').BytesIO(frame)))


@app.post('/api/stream/vision/frame')
async def ingest_vision_frame(file: UploadFile = File(...)) -> dict:
    global last_vision_hash, last_vision_description
    frame = await file.read()
    if not frame or len(frame) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Frame is empty or larger than 12 MB')
    frame_hash = hashlib.sha256(frame).hexdigest()
    if frame_hash == last_vision_hash:
        return {'accepted': False, 'duplicate': True, 'reasoning': last_vision_description}
    last_vision_hash = frame_hash
    try:
        async with vision_semaphore:
            decision = await asyncio.wait_for(gemini_service.decide(bot_name=twitch_service.bot_username or 'Зеточка', current_lang='ru', mood=mood_service.snapshot(), transcript=streamer_context(), chat_history=[], frame=frame, frame_description=last_vision_description or 'Current stream screenshot attached.'), timeout=45)
    except asyncio.TimeoutError as error:
        raise HTTPException(status_code=504, detail='Vision analysis timed out') from error
    last_vision_description = str(decision.get('reasoning', 'Frame analyzed'))[:1800]
    with SessionLocal.begin() as db:
        persona = db.query(PersonaSettings).first()
        if persona:
            persona.context_summary = last_vision_description
    await hub.broadcast({'type': 'VISION_FRAME_ANALYZED', 'description': last_vision_description, 'confidence': 0})
    return decision


@app.post('/api/twitch/irc/connect')
async def connect_irc(request: IrcConnectRequest) -> dict:
    global irc_task
    channel_name = normalize_channel_name(request.channel)
    bot_username = request.bot_username.strip()
    bot_token = request.bot_token.strip()

    if not channel_name:
        error = 'Не удалось подключиться к каналу: имя канала пустое.'
        await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': error})
        return {'connected': False, 'channel': '', 'bot_username': bot_username, 'message': error, 'mode': 'invalid-channel'}

    if not bot_token:
        error = f"Не удалось подключиться к каналу '{channel_name}'. Убедитесь, что логин канала указан без ошибок и OAuth-токен активен."
        await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': error})
        return {'connected': False, 'channel': channel_name, 'bot_username': bot_username, 'message': error, 'mode': 'invalid-oauth'}

    try:
        settings.twitch_bot_token = bot_token
        settings.twitch_bot_username = bot_username
        await start_twitch_session(channel_name, 'irc_join')
        result = await twitch_service.connect()
        connected = bool(twitch_service.connected)
        message = (
            f'[IRC] Connected to #{channel_name} as @{bot_username}'
            if connected
            else f'[IRC] Connecting to #{channel_name} as @{bot_username}'
        )
        await hub.broadcast({'type': 'IRC_STATUS', 'connected': connected, 'message': message})
        return {'connected': connected, 'channel': channel_name, 'bot_username': bot_username, 'message': message, 'mode': result['mode']}
    except Exception as exc:
        logger.exception('IRC reconnect failed for channel=%s', channel_name)
        message = f"Не удалось подключиться к каналу '{channel_name}'. Убедитесь, что логин канала указан без ошибок и OAuth-токен активен."
        await hub.broadcast({'type': 'SYSTEM_ERROR', 'message': message})
        return {'connected': False, 'channel': channel_name, 'bot_username': bot_username, 'message': message, 'mode': 'error', 'details': str(exc)}


@app.post('/api/overlay/meme')
async def overlay_meme(request: MemeRequest) -> dict:
    payload = {'type': 'TRIGGER_MEME_FX', **request.model_dump()}
    await hub.broadcast(payload)
    return payload


@app.post('/api/auth/twitch/callback')
async def twitch_auth_callback(request: TwitchCallbackRequest) -> dict:
    client_id = (request.client_id or settings.twitch_client_id or DEFAULT_TWITCH_CLIENT_ID).strip()
    if not client_id:
        raise HTTPException(status_code=503, detail='Twitch OAuth application is not configured on the server')
    try:
        verified_user = await verify_twitch_credentials(
            request.user.get('login', request.user.get('display_name', '')),
            client_id,
            request.token,
        )
    except TwitchVerificationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    with SessionLocal.begin() as db:
        account = db.query(Account).filter(Account.account_type == request.account_type).first()
        if not account:
            account = Account(account_type=request.account_type)
            db.add(account)
        account.username = verified_user['username']
        account.display_name = verified_user['display_name']
        account.profile_image_url = request.user.get('profile_image_url', '')
        account.client_id = client_id
        account.token_encrypted = encrypt(request.token, settings.local_encryption_key)
        account.connected = True
        account.moderator = request.account_type == 'bot'
    hydrate_runtime_credentials()
    if request.account_type == 'bot' and settings.twitch_bot_token and settings.twitch_channel:
        await start_twitch_session(normalize_channel_name(settings.twitch_channel), 'irc_bot_oauth_login')
    elif request.account_type == 'broadcaster':
        twitch_service.mark_disconnected()
    return {'connected': True, 'account_type': request.account_type, 'user': {**request.user, **verified_user}}


@app.post('/api/auth/twitch')
async def twitch_auth(request: TwitchCallbackRequest) -> dict:
    return await twitch_auth_callback(request)


@app.get('/api/queue')
async def get_queue() -> list[dict]:
    with SessionLocal() as db:
        return [{'id': item.id, 'user': item.user, 'message': item.message, 'response': item.response, 'confidence': item.confidence, 'time': 'now'} for item in db.query(QueueItem).filter(QueueItem.status == 'pending').all()]


async def queue_action(item_id: int, action: str, response: str | None = None) -> dict:
    with SessionLocal.begin() as db:
        item = db.get(QueueItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail='Queue item not found')
        if response:
            item.response = response
        message_to_send = item.response
        item.status = 'sending' if action in ('approved', 'sent') else action
        item_id = item.id
    if action in ('approved', 'sent'):
        try:
            dispatch = await asyncio.wait_for(twitch_service.send_message(message_to_send), timeout=10)
        except asyncio.TimeoutError:
            dispatch = {'sent': False, 'mode': 'timeout'}
        with SessionLocal.begin() as db:
            item = db.get(QueueItem, item_id)
            if not item:
                raise HTTPException(status_code=404, detail='Queue item not found')
            if not dispatch['sent']:
                item.status = 'pending'
                db.add(Log(log_type='warning', text=f'Queue item {item.id} kept pending: {dispatch.get("mode", "offline")}'))
                detail = dispatch.get('error') or dispatch.get('mode', 'offline')
                result = {'id': item.id, 'status': item.status, 'message': f'Twitch send failed: {detail}'}
            else:
                item.status = action
                db.add(Log(log_type='action', text=f'Queue item {action}: {item.id}'))
                result = {'id': item.id, 'status': item.status, 'message': 'Sent to Twitch'}
    else:
        with SessionLocal.begin() as db:
            item = db.get(QueueItem, item_id)
            if not item:
                raise HTTPException(status_code=404, detail='Queue item not found')
            db.add(Log(log_type='safety', text=f'Queue item {action}: {item.id}'))
            result = {'id': item.id, 'status': action, 'message': 'Queue item rejected'}
    await hub.broadcast({'type': 'queue', 'queue': await get_queue()})
    return result


@app.post('/api/queue/{item_id}/approve')
async def approve_queue(item_id: int, request: QueueAction = QueueAction()) -> dict:
    return await queue_action(item_id, 'approved', request.response)


@app.post('/api/queue/{item_id}/reject')
async def reject_queue(item_id: int) -> dict:
    return await queue_action(item_id, 'rejected')


@app.post('/api/queue/{item_id}/jeetbot')
async def send_queue(item_id: int) -> dict:
    return await queue_action(item_id, 'sent')


@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket) -> None:
    await hub.add(websocket)
    await websocket.send_json(state_payload())
    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get('type')
            if message_type == 'PING':
                await websocket.send_json({'type': 'PONG'})
                continue
            if message_type == 'PONG':
                continue
            if message_type == 'mood_event':
                mood = mood_service.apply_event(message.get('event', 'silence'))
                with SessionLocal.begin() as db:
                    record = db.query(Mood).first()
                    record.hype, record.sarcasm, record.empathy, record.label = mood['hype'], mood['sarcasm'], mood['empathy'], mood['label']
                    db.add(Log(log_type='reasoning', text=f'Mood event: {message.get("event", "silence")}'))
                await hub.broadcast({'type': 'MOOD_STATE_CHANGED', 'mood': mood})
            elif message_type in {'BOT_START_TALKING', 'BOT_STOP_TALKING'}:
                await hub.broadcast(message)
            elif message_type == 'decision':
                transcript = message.get('transcript', '')
                remember_streamer_transcript(transcript)
                decision = await gemini_service.decide(bot_name=message.get('bot_name', 'Sentinel'), current_lang=message.get('language', 'en'), mood=mood_service.snapshot(), transcript=streamer_context(), chat_history=message.get('chat_history', []), frame_description=message.get('frame_description', ''))
                await websocket.send_json({'type': 'decision', 'decision': decision})
    except WebSocketDisconnect:
        hub.remove(websocket)
