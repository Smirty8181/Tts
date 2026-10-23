from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)


class ObsService:
    """Small OBS WebSocket 5.x client with safe reconnect and screenshot support."""

    def __init__(self) -> None:
        self.url = 'ws://127.0.0.1:4455'
        self.password = ''
        self.enabled = False
        self.connected = False
        self.last_error = ''
        self._socket: Any = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    def configure(self, url: str, password: str, enabled: bool) -> None:
        self.url = (url or 'ws://127.0.0.1:4455').strip()
        self.password = password or ''
        self.enabled = bool(enabled)

    async def _authenticate(self, socket: Any, hello: dict) -> None:
        identify: dict[str, Any] = {'op': 1, 'd': {'rpcVersion': 1}}
        auth = hello.get('d', {}).get('authentication')
        if auth and self.password:
            secret = base64.b64encode(hashlib.sha256((self.password + auth['salt']).encode()).digest()).decode()
            auth_value = base64.b64encode(hashlib.sha256((secret + auth['challenge']).encode()).digest()).decode()
            identify['d']['authentication'] = auth_value
        await socket.send(json.dumps(identify))
        response = json.loads(await asyncio.wait_for(socket.recv(), timeout=8))
        if response.get('op') != 2:
            raise RuntimeError(response.get('d', {}).get('error', 'OBS authentication failed'))

    async def connect(self) -> bool:
        if not self.enabled:
            self.connected = False
            return False
        try:
            import websockets
            async with self._lock:
                if self._socket:
                    return self.connected
                socket = await websockets.connect(self.url, open_timeout=8, close_timeout=2, ping_interval=20)
                hello = json.loads(await asyncio.wait_for(socket.recv(), timeout=8))
                await self._authenticate(socket, hello)
                self._socket = socket
                self.connected = True
                self.last_error = ''
                return True
        except Exception as error:
            self.connected = False
            self.last_error = str(error)
            self._socket = None
            logger.warning('OBS connection failed: %s', error)
            return False

    async def disconnect(self) -> None:
        socket, self._socket = self._socket, None
        self.connected = False
        if socket:
            try:
                await socket.close()
            except Exception:
                pass

    async def request(self, request_type: str, request_data: dict | None = None) -> dict:
        if not await self.connect():
            raise RuntimeError(self.last_error or 'OBS is disabled')
        async with self._request_lock:
            self._request_id += 1
            request_id = str(self._request_id)
            try:
                await asyncio.wait_for(self._socket.send(json.dumps({'op': 6, 'd': {'requestType': request_type, 'requestId': request_id, 'requestData': request_data or {}}})), timeout=5)
                while True:
                    response = json.loads(await asyncio.wait_for(self._socket.recv(), timeout=12))
                    if response.get('op') != 7 or response.get('d', {}).get('requestId') != request_id:
                        continue
                    data = response.get('d', {})
                    if not data.get('requestStatus', {}).get('result', False):
                        raise RuntimeError(data.get('requestStatus', {}).get('comment', 'OBS request failed'))
                    return data.get('responseData', {})
            except Exception:
                self.connected = False
                await self.disconnect()
                raise

    async def screenshot(self, source: str = '') -> str:
        data = await self.request('GetSourceScreenshot', {'sourceName': source, 'imageFormat': 'jpg', 'imageWidth': 1280})
        return data.get('imageData', '')

    def status(self) -> dict:
        return {'enabled': self.enabled, 'connected': self.connected, 'url': self.url, 'last_error': self.last_error}
