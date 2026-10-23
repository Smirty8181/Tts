import asyncio
import base64
import hashlib
import os
from pathlib import Path

import pytest

os.environ['DATABASE_PATH'] = str(Path(__file__).resolve().with_name('test_database.db'))
os.environ['LOCAL_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(hashlib.sha256(b'twitch-sentinel-tests').digest()).decode()

from fastapi.testclient import TestClient

from app.database import Account, PersonaSettings, SessionLocal, decrypt, encrypt
from app.main import app, normalize_channel_name, twitch_service
from app.main import parse_streamer_command
from app.config import get_settings


def test_encrypt_requires_configured_key():
    with pytest.raises(ValueError, match='LOCAL_ENCRYPTION_KEY'):
        encrypt('test secret', '')


def test_channel_name_is_normalized_and_validated():
    assert normalize_channel_name(' #S_MIRT_Y ') == 's_mirt_y'


def test_streamer_voice_requires_wake_word():
    assert parse_streamer_command('как дела в игре?') is None
    command = parse_streamer_command('Зеточка, что думаешь об этом моменте?')
    assert command is not None
    assert command.is_streamer is True
    assert command.prompt == 'что думаешь об этом моменте'


def test_streamer_voice_accepts_common_stt_wake_word_error():
    command = parse_streamer_command('зетачка подскажи следующий ход')
    assert command is not None
    assert command.prompt == 'подскажи следующий ход'


def test_health_and_persistent_settings():
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        payload = {'bot_name': 'QA Sentinel', 'system_prompt': 'Respond briefly.', 'temperature': 0.55, 'cooldown': 4, 'attention_threshold': 80, 'jeetbot_endpoint': 'http://jeetbot.local', 'voice_id': 'JEE-07', 'speed': 1.1, 'pitch': 0, 'tos_guard': True, 'auto_reply': False}
        assert client.put('/api/settings', json=payload).status_code == 200
        assert client.get('/api/settings').json()['bot_name'] == 'QA Sentinel'
        assert client.get('/api/settings').json()['auto_reply'] is False


def test_gemini_model_name_resolves_to_supported_latest():
    from app.services.llm_provider_service import _resolved_gemini_model_name
    assert _resolved_gemini_model_name('gemini-2.5-flash') == 'gemini-3.6-flash'
    assert _resolved_gemini_model_name('gemini-3.6-flash') == 'gemini-3.6-flash'


def test_v1_models_endpoint_returns_model_list():
    with TestClient(app) as client:
        response = client.get('/v1/models')
        assert response.status_code == 200
        payload = response.json()
        assert payload['object'] == 'list'
        assert any(item['id'] == 'gemini-3.6-flash' for item in payload['data'])


def test_settings_api_accepts_gemini_key_update():
    with TestClient(app) as client:
        response = client.put('/api/settings', json={'gemini_api_key': 'new-gemini-key'})
        assert response.status_code == 200
        assert get_settings().gemini_api_key == 'new-gemini-key'


def test_mood_memory_and_queue_actions():
    with TestClient(app) as client:
        assert client.post('/api/mood/event', json={'event': 'victory'}).json()['hype'] == 98
        memory = client.post('/api/memory', json={'type': 'TEST', 'value': 'Persistent test memory'}).json()
        assert client.get('/api/memory').json()['long_term'][-1]['value'] == 'Persistent test memory'
        assert client.delete(f"/api/memory/{memory['id']}").status_code == 200
        twitch_service.connected = True
        twitch_service.client = object()
        original_send = twitch_service.send_message
        async def send_for_test(message):
            return {'sent': True, 'mode': 'test', 'message': message}
        twitch_service.send_message = send_for_test
        try:
            from app.database import QueueItem, SessionLocal
            with SessionLocal.begin() as db:
                item = QueueItem(user='qa_viewer', message='hello', response='Approved response')
                db.add(item)
                db.flush()
                item_id = item.id
            response = client.post(f'/api/queue/{item_id}/approve')
            assert response.status_code == 200
            assert response.json()['status'] == 'approved'
            assert response.json()['message'] == 'Sent to Twitch'
        finally:
            twitch_service.send_message = original_send


def test_handle_trigger_does_not_touch_detached_queue_item(monkeypatch):
    from app import main

    async def fake_generate_provider_reply(*, provider, api_key, system_prompt, bot_name, author_name, user_message, temperature):
        return 'Reply from test AI'

    async def fake_broadcast(payload):
        return None

    monkeypatch.setattr(main, 'generate_provider_reply', fake_generate_provider_reply)
    monkeypatch.setattr(main.hub, 'broadcast', fake_broadcast)
    async def fake_send_message(message):
        return {'sent': True, 'mode': 'test', 'message': message}
    monkeypatch.setattr(main.twitch_service, 'send_message', fake_send_message)
    main.twitch_service.connected = True
    main.twitch_service.settings.twitch_bot_token = 'test-token'

    with SessionLocal.begin() as db:
        persona = db.query(PersonaSettings).first()
        if persona is None:
            persona = PersonaSettings()
            db.add(persona)
        persona.bot_name = 'GuardBot'
        persona.auto_reply = True
        persona.system_prompt = 'Reply briefly.'
        persona.temperature = 0.5
        persona.llm_provider = 'gemini'

    command = type('Cmd', (), {'viewer_name': 'qa_viewer', 'prompt': 'hello there', 'command': '!ask'})()
    asyncio.run(main.handle_trigger(command))

    with SessionLocal.begin() as db:
        item = db.query(main.QueueItem).filter_by(user='qa_viewer').order_by(main.QueueItem.id.desc()).first()
        assert item is not None
        assert item.response == 'Reply from test AI'


def test_websocket_initial_state_and_telemetry():
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as websocket:
            initial = websocket.receive_json()
            assert initial['type'] == 'state'
            websocket.send_json({'type': 'mood_event', 'event': 'silence'})
            update = websocket.receive_json()
            assert update['type'] == 'MOOD_STATE_CHANGED'


def test_llm_verify_persists_keys_and_keeps_existing_on_timeout(monkeypatch):
    settings = get_settings()
    with SessionLocal.begin() as db:
        persona = db.query(PersonaSettings).first()
        persona.gemini_key_encrypted = encrypt('old-gemini-key', settings.local_encryption_key)
        persona.deepseek_key_encrypted = encrypt('old-deepseek-key', settings.local_encryption_key)
        persona.openai_key_encrypted = encrypt('old-openai-key', settings.local_encryption_key)

    async def fake_verify(provider, api_key):
        return {'valid': True, 'provider': provider}

    monkeypatch.setattr('app.main.verify_provider_key', fake_verify)

    with TestClient(app) as client:
        response = client.post('/api/llm/verify', json={'provider': 'gemini', 'api_key': 'new-gemini-key'})
        assert response.status_code == 200
        with SessionLocal.begin() as db:
            persona = db.query(PersonaSettings).first()
            assert decrypt(persona.gemini_key_encrypted, settings.local_encryption_key) == 'new-gemini-key'

    with TestClient(app) as client:
        async def fake_timeout(provider, api_key):
            raise RuntimeError('temporary timeout')

        monkeypatch.setattr('app.main.verify_provider_key', fake_timeout)
        response = client.post('/api/llm/verify', json={'provider': 'deepseek', 'api_key': 'timeout-key'})
        assert response.status_code == 504
        with SessionLocal.begin() as db:
            persona = db.query(PersonaSettings).first()
            assert decrypt(persona.deepseek_key_encrypted, settings.local_encryption_key) == 'old-deepseek-key'


def test_runtime_credentials_are_restored_from_db():
    settings = get_settings()
    with SessionLocal.begin() as db:
        account = db.query(Account).filter(Account.account_type == 'broadcaster').first()
        if account is None:
            account = Account(account_type='broadcaster')
            db.add(account)
        account.username = 'qa_channel'
        account.client_id = 'client-123'
        account.token_encrypted = encrypt('broadcaster-token', settings.local_encryption_key)
        account.connected = True

        bot = db.query(Account).filter(Account.account_type == 'bot').first()
        if bot is None:
            bot = Account(account_type='bot')
            db.add(bot)
        bot.username = 'qa_bot'
        bot.client_id = 'bot-client-123'
        bot.token_encrypted = encrypt('bot-token', settings.local_encryption_key)
        bot.connected = True

    from app.main import hydrate_runtime_credentials

    hydrate_runtime_credentials()

    assert settings.twitch_channel == 'qa_channel'
    assert settings.twitch_bot_token == 'bot-token'
    assert settings.twitch_bot_username == 'qa_bot'


def test_test_notification_requires_chat_and_reports_status():
    with TestClient(app) as client:
        response = client.post('/api/notifications/test', json={'message': 'hello from test'})
        assert response.status_code == 200
        payload = response.json()
        assert 'Тестовое сообщение отправлено в чат' in payload['message'] or 'Не удалось отправить тестовое сообщение' in payload['message']


def test_health_exposes_service_status_and_metrics():
    with TestClient(app) as client:
        health = client.get('/health')
        assert health.status_code == 200
        assert set(('api', 'database', 'twitch', 'obs', 'llm')).issubset(health.json()['services'])
        metrics = client.get('/api/metrics')
        assert metrics.status_code == 200
        assert 'llm_calls' in metrics.json()


def test_vision_description_is_deduplicated_and_persisted():
    with TestClient(app) as client:
        payload = {'description': 'New scene: boss fight', 'confidence': 88}
        first = client.post('/api/stream/vision', json=payload)
        second = client.post('/api/stream/vision', json=payload)
        assert first.json()['accepted'] is True
        assert second.json()['duplicate'] is True
        assert client.get('/api/settings').json()['bot_name']


def test_chat_memory_clear_endpoint_is_scoped():
    with TestClient(app) as client:
        client.post('/api/sandbox/message', json={'viewer_name': 'memory_test', 'message': 'hello'})
        response = client.delete('/api/memory/chat?username=memory_test')
        assert response.status_code == 200
        assert response.json()['deleted'] >= 1
