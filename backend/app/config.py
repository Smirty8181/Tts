from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = 'Twitch Sentinel API'
    environment: str = 'development'
    host: str = '0.0.0.0'
    port: int = 8000
    cors_origins: str = 'http://localhost:5173,http://localhost:4173'
    gemini_api_key: str = ''
    deepseek_api_key: str = ''
    openai_api_key: str = ''
    groq_api_key: str = ''
    elevenlabs_api_key: str = ''
    groq_model: str = 'openai/gpt-oss-20b'
    gemini_model: str = 'gemini-2.0-flash'
    twitch_client_id: str = 'gragq9yg68pkionhexl3zlgca9rj2p'
    twitch_client_secret: str = ''
    twitch_broadcaster_token: str = ''
    twitch_bot_token: str = ''
    twitch_channel: str = ''
    twitch_bot_username: str = ''
    youtube_channel: str = ''
    youtube_token: str = ''
    obs_url: str = 'ws://127.0.0.1:4455'
    obs_password: str = ''
    obs_enabled: bool = False
    obs_capture_interval: float = 5.0
    jeetbot_webhook_url: str = ''
    jeetbot_ws_url: str = ''
    jeetbot_api_key: str = ''
    local_encryption_key: str = ''
    llm_http_proxy: str = ''
    llm_https_proxy: str = ''
    llm_socks5_proxy: str = ''

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def llm_proxy(self) -> str | None:
        return self.llm_socks5_proxy.strip() or self.llm_https_proxy.strip() or self.llm_http_proxy.strip() or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
