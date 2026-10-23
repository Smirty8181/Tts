from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import base64
import hashlib
import hmac
import os
import secrets

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, event, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.environ.get('DATABASE_PATH', BASE_DIR / 'database.db'))
DATABASE_URL = f'sqlite:///{DATABASE_PATH.as_posix()}'

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
@event.listens_for(engine, 'connect')
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_type: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), default='')
    client_id: Mapped[str] = mapped_column(String(200), default='')
    token_encrypted: Mapped[str] = mapped_column(Text, default='')
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    moderator: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str] = mapped_column(String(100), default='')
    profile_image_url: Mapped[str] = mapped_column(Text, default='')
    live: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PersonaSettings(Base):
    __tablename__ = 'persona_settings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_name: Mapped[str] = mapped_column(String(100), default='Sentinel')
    system_prompt: Mapped[str] = mapped_column(Text, default='Be sharp, observant, and concise.')
    temperature: Mapped[float] = mapped_column(Float, default=0.68)
    cooldown: Mapped[float] = mapped_column(Float, default=3.5)
    attention_threshold: Mapped[int] = mapped_column(Integer, default=72)
    jeetbot_endpoint: Mapped[str] = mapped_column(String(500), default='')
    jeetbot_webhook_url: Mapped[str] = mapped_column(String(500), default='')
    jeetbot_api_key_encrypted: Mapped[str] = mapped_column(Text, default='')
    voice_id: Mapped[str] = mapped_column(String(100), default='JEE-02')
    speed: Mapped[float] = mapped_column(Float, default=1.05)
    pitch: Mapped[float] = mapped_column(Float, default=0)
    tos_guard: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_provider: Mapped[str] = mapped_column(String(30), default='gemini')
    avatar_idle: Mapped[str] = mapped_column(Text, default='')
    avatar_talking: Mapped[str] = mapped_column(Text, default='')
    avatar_rage: Mapped[str] = mapped_column(Text, default='')
    avatar_hype: Mapped[str] = mapped_column(Text, default='')
    gemini_model: Mapped[str] = mapped_column(String(80), default='gemini-2.0-flash')
    gemini_key_encrypted: Mapped[str] = mapped_column(Text, default='')
    deepseek_key_encrypted: Mapped[str] = mapped_column(Text, default='')
    openai_key_encrypted: Mapped[str] = mapped_column(Text, default='')
    groq_key_encrypted: Mapped[str] = mapped_column(Text, default='')
    groq_model: Mapped[str] = mapped_column(String(100), default='openai/gpt-oss-20b')
    adaptive_context: Mapped[str] = mapped_column(Text, default='')
    context_summary: Mapped[str] = mapped_column(Text, default='')
    response_triggers: Mapped[str] = mapped_column(Text, default='["Зетка", "Зеточка", "НейроЗетка", "neyrozetka", "Зет"]')
    elevenlabs_key_encrypted: Mapped[str] = mapped_column(Text, default='')
    elevenlabs_voice_id: Mapped[str] = mapped_column(String(100), default='')
    tts_provider: Mapped[str] = mapped_column(String(30), default='jeetbot')
    youtube_channel: Mapped[str] = mapped_column(String(200), default='')
    youtube_token_encrypted: Mapped[str] = mapped_column(Text, default='')
    obs_url: Mapped[str] = mapped_column(String(500), default='ws://127.0.0.1:4455')
    obs_password_encrypted: Mapped[str] = mapped_column(Text, default='')
    obs_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    obs_capture_interval: Mapped[float] = mapped_column(Float, default=5.0)


class StreamerProfile(Base):
    __tablename__ = 'streamer_profiles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    preferences: Mapped[str] = mapped_column(Text, default='')
    facts: Mapped[str] = mapped_column(Text, default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Memory(Base):
    __tablename__ = 'memories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_type: Mapped[str] = mapped_column(String(20), default='NOTE')
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ViewerProfile(Base):
    __tablename__ = 'viewer_profiles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    notes: Mapped[str] = mapped_column(Text, default='')
    preferences: Mapped[str] = mapped_column(Text, default='')
    summary: Mapped[str] = mapped_column(Text, default='')


class ViewerMessage(Base):
    __tablename__ = 'viewer_messages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_mention: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ChatMemory(Base):
    __tablename__ = 'chat_memories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), index=True, default='')
    role: Mapped[str] = mapped_column(String(20), default='viewer')
    content: Mapped[str] = mapped_column(Text)
    is_mention: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    __table_args__ = (Index('ix_chat_memories_user_created', 'username', 'created_at'),)


class Log(Base):
    __tablename__ = 'logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_type: Mapped[str] = mapped_column(String(20), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class LlmObservation(Base):
    __tablename__ = 'llm_observations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    mode: Mapped[str] = mapped_column(String(20), default='chat')
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(200), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class QueueItem(Base):
    __tablename__ = 'queue_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(Integer, default=90)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('ix_queue_items_status_created', 'status', 'created_at'),)


class Mood(Base):
    __tablename__ = 'mood_state'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hype: Mapped[int] = mapped_column(Integer, default=78)
    sarcasm: Mapped[int] = mapped_column(Integer, default=42)
    empathy: Mapped[int] = mapped_column(Integer, default=64)
    label: Mapped[str] = mapped_column(String(30), default='hyped')


def init_db() -> None:
    Base.metadata.create_all(engine)
    migrate_persona_columns()
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_viewer_messages_user_created ON viewer_messages(username, created_at)')
        connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_logs_type_created ON logs(log_type, created_at)')
        connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_queue_items_status_created ON queue_items(status, created_at)')
    with SessionLocal.begin() as session:
        if not session.query(PersonaSettings).first():
            session.add(PersonaSettings())
        if not session.query(Mood).first():
            session.add(Mood())
        persona = session.query(PersonaSettings).first()
        if not session.query(Memory).first():
            session.add_all([Memory(memory_type='LORE', value='Streamer always blames the chair after a misplay.'), Memory(memory_type='MEME', value='The 1 HP clutch is now called the Lazarus.')])
        cleanup_before = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year - 1)
        session.query(Log).filter(Log.created_at < cleanup_before).delete()
        session.query(LlmObservation).filter(LlmObservation.created_at < cleanup_before).delete()
        session.query(ViewerMessage).filter(ViewerMessage.created_at < cleanup_before).delete()
        session.query(ChatMemory).filter(ChatMemory.created_at < cleanup_before).delete()


def migrate_persona_columns() -> None:
    columns = {
        'llm_provider': "VARCHAR(30) DEFAULT 'gemini'",
        'jeetbot_webhook_url': "VARCHAR(500) DEFAULT ''",
        'avatar_idle': "TEXT DEFAULT ''",
        'avatar_talking': "TEXT DEFAULT ''",
        'avatar_rage': "TEXT DEFAULT ''",
        'avatar_hype': "TEXT DEFAULT ''",
        'gemini_model': "VARCHAR(80) DEFAULT 'gemini-2.0-flash'",
        'gemini_key_encrypted': "TEXT DEFAULT ''",
        'deepseek_key_encrypted': "TEXT DEFAULT ''",
        'openai_key_encrypted': "TEXT DEFAULT ''",
        'groq_key_encrypted': "TEXT DEFAULT ''",
        'groq_model': "VARCHAR(100) DEFAULT 'openai/gpt-oss-20b'",
        'adaptive_context': "TEXT DEFAULT ''",
        'context_summary': "TEXT DEFAULT ''",
        'response_triggers': "TEXT DEFAULT '[\"Зетка\", \"Зеточка\", \"НейроЗетка\", \"neyrozetka\", \"Зет\"]'",
        'elevenlabs_key_encrypted': "TEXT DEFAULT ''",
        'elevenlabs_voice_id': "VARCHAR(100) DEFAULT ''",
        'tts_provider': "VARCHAR(30) DEFAULT 'jeetbot'",
        'youtube_channel': "VARCHAR(200) DEFAULT ''",
        'youtube_token_encrypted': "TEXT DEFAULT ''",
        'obs_url': "VARCHAR(500) DEFAULT 'ws://127.0.0.1:4455'",
        'obs_password_encrypted': "TEXT DEFAULT ''",
        'obs_enabled': "BOOLEAN DEFAULT 0",
        'obs_capture_interval': "FLOAT DEFAULT 5.0",
    }
    account_columns = {'display_name': "VARCHAR(100) DEFAULT ''", 'profile_image_url': "TEXT DEFAULT ''", 'live': "BOOLEAN DEFAULT 0"}
    with engine.begin() as connection:
        existing = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(persona_settings)')}
        for name, definition in columns.items():
            if name not in existing:
                connection.exec_driver_sql(f'ALTER TABLE persona_settings ADD COLUMN {name} {definition}')
        profile_columns = {'preferences': "TEXT DEFAULT ''", 'summary': "TEXT DEFAULT ''"}
        existing_viewer = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(viewer_profiles)')}
        for name, definition in profile_columns.items():
            if name not in existing_viewer:
                connection.exec_driver_sql(f'ALTER TABLE viewer_profiles ADD COLUMN {name} {definition}')
        connection.exec_driver_sql(
            "UPDATE persona_settings SET groq_model = 'openai/gpt-oss-20b' "
            "WHERE groq_model IS NULL OR trim(groq_model) = '' "
            "OR replace(replace(trim(groq_model), char(34), ''), char(39), '') IN "
            "('llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'llama-3.1-70b-versatile')"
        )
        existing_accounts = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(accounts)')}
        for name, definition in account_columns.items():
            if name not in existing_accounts:
                connection.exec_driver_sql(f'ALTER TABLE accounts ADD COLUMN {name} {definition}')


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def encrypt(value: str, key: str) -> str:
    if not value:
        return ''
    if not key:
        raise ValueError('LOCAL_ENCRYPTION_KEY must be configured before storing credentials')
    if Fernet:
        return Fernet(key.encode()).encrypt(value.encode()).decode()
    key_bytes = hashlib.sha256(key.encode()).digest()
    nonce = secrets.token_bytes(16)
    encrypted = bytes(char ^ key_bytes[index % len(key_bytes)] ^ nonce[index % len(nonce)] for index, char in enumerate(value.encode()))
    payload = nonce + encrypted
    signature = hmac.new(key_bytes, payload, hashlib.sha256).digest()
    return 'local:' + base64.urlsafe_b64encode(payload + signature).decode()


def decrypt(value: str, key: str) -> str:
    if not value:
        return ''
    if Fernet and not value.startswith('local:'):
        return Fernet(key.encode()).decrypt(value.encode()).decode()
    payload = base64.urlsafe_b64decode(value.removeprefix('local:'))
    key_bytes = hashlib.sha256(key.encode()).digest()
    content, signature = payload[:-32], payload[-32:]
    if not hmac.compare_digest(signature, hmac.new(key_bytes, content, hashlib.sha256).digest()):
        raise ValueError('Credential integrity check failed')
    nonce, encrypted = content[:16], content[16:]
    return bytes(char ^ key_bytes[index % len(key_bytes)] ^ nonce[index % len(nonce)] for index, char in enumerate(encrypted)).decode()
