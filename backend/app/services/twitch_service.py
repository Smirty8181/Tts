from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import asyncio

from app.config import Settings

try:
    from twitchio.ext import commands
except ImportError:
    commands = None


@dataclass
class ChatMessage:
    id: int
    user: str
    message: str
    color: str
    time: str
    badge: str = ''


class TwitchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connected = False
        self.messages: list[ChatMessage] = []
        self._next_id = 1
        self.on_message = None
        self.client = None
        self.channel = settings.twitch_channel
        self.bot_username = settings.twitch_bot_username
        self.last_error = ''
        self.join_blocked = False
        self.ready_event = asyncio.Event()
        if commands and settings.twitch_bot_token and settings.twitch_channel:
            service = self

            class SentinelTwitchBot(commands.Bot):
                def __init__(self) -> None:
                    super().__init__(token=settings.twitch_bot_token, prefix='!', initial_channels=[settings.twitch_channel])

                async def event_ready(self) -> None:
                    service.connected = True

                async def event_message(self, message) -> None:
                    if getattr(message, 'echo', False):
                        return
                    author = getattr(message, 'author', None)
                    service.ingest_message(
                        getattr(author, 'name', 'viewer'),
                        getattr(message, 'content', ''),
                        getattr(author, 'color', None) or '#60a5fa',
                    )
                    if service.on_message:
                        service.on_message(getattr(author, 'name', 'viewer'), getattr(message, 'content', ''))

            self.client = SentinelTwitchBot()

    def configure(self, token: str, channel: str, bot_username: str) -> None:
        token = token.strip()
        if token and not token.lower().startswith('oauth:'):
            token = f'oauth:{token}'
        self.settings.twitch_bot_token = token
        self.channel = channel
        self.bot_username = bot_username
        self.connected = False
        self.join_blocked = False
        self.ready_event = asyncio.Event()
        if not commands or not token or not channel:
            return
        service = self

        class RuntimeTwitchBot(commands.Bot):
            def __init__(self) -> None:
                super().__init__(token=token, prefix='!', initial_channels=[channel])

            async def event_ready(self) -> None:
                service.connected = True
                service.last_error = ''
                service.ready_event.set()
                try:
                    asyncio.create_task(hub.broadcast({'type': 'IRC_STATUS', 'connected': True, 'message': f'[IRC] Connected to #{service.channel}'}))
                except NameError:
                    pass

            async def event_error(self, error, data=None) -> None:
                service.connected = False
                service.last_error = str(error)
                if 'unable to be joined' in service.last_error.lower() or 'channel is suspended' in service.last_error.lower():
                    service.join_blocked = True
                try:
                    asyncio.create_task(hub.broadcast({'type': 'IRC_STATUS', 'connected': False, 'message': f'[IRC] {error}'}))
                except NameError:
                    pass

            async def event_disconnect(self) -> None:
                service.connected = False
                service.ready_event.clear()
                try:
                    asyncio.create_task(hub.broadcast({'type': 'IRC_STATUS', 'connected': False, 'message': '[IRC] Disconnected; reconnecting'}))
                except NameError:
                    pass

            async def event_message(self, message) -> None:
                if getattr(message, 'echo', False):
                    return
                author = getattr(message, 'author', None)
                service.ingest_message(getattr(author, 'name', 'viewer'), getattr(message, 'content', ''), getattr(author, 'color', None) or '#60a5fa')
                if service.on_message:
                    service.on_message(getattr(author, 'name', 'viewer'), getattr(message, 'content', ''))

        self.client = RuntimeTwitchBot()
        self.ready_event = asyncio.Event()

    def mark_disconnected(self) -> None:
        self.connected = False
        self.ready_event.clear()

    async def connect(self) -> dict:
        configured = bool(self.channel and self.settings.twitch_bot_token)
        if configured and self.client:
            if not self.connected:
                try:
                    await asyncio.wait_for(self.ready_event.wait(), timeout=8)
                except asyncio.TimeoutError:
                    return {'connected': False, 'channel': self.channel, 'mode': 'twitchio-connecting'}
            return {'connected': self.connected, 'channel': self.channel, 'mode': 'twitchio-ready'}
        self.connected = False
        return {'connected': False, 'channel': self.settings.twitch_channel, 'mode': 'offline'}

    async def send_message(self, message: str) -> dict:
        if not self.client or not self.settings.twitch_bot_token:
            return {'sent': False, 'mode': 'unauthenticated', 'message': message}
        if not self.connected:
            try:
                await asyncio.wait_for(self.ready_event.wait(), timeout=8)
            except asyncio.TimeoutError:
                return {'sent': False, 'mode': 'disconnected', 'message': message}
        channel = self.client.get_channel(self.channel)
        if not channel:
            self.mark_disconnected()
            return {'sent': False, 'mode': 'channel-not-joined', 'message': message}
        try:
            await channel.send(message)
        except Exception as error:
            self.mark_disconnected()
            return {'sent': False, 'mode': 'disconnected', 'message': message, 'error': str(error)}
        return {'sent': True, 'mode': 'twitchio', 'message': message}

    def ingest_message(self, user: str, message: str, color: str = '#60a5fa', badge: str = '') -> dict:
        item = ChatMessage(self._next_id, user, message, color, datetime.now(timezone.utc).strftime('%H:%M:%S'), badge)
        self._next_id += 1
        self.messages.append(item)
        self.messages = self.messages[-100:]
        return asdict(item)
