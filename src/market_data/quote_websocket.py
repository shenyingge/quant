"""WebSocket server for real-time quote subscription."""

import asyncio
import json
import threading
from typing import Dict, Set

import redis
import websockets
from websockets.server import WebSocketServerProtocol

from src.config import settings
from src.logger_config import configured_logger as logger


class QuoteWebSocketServer:
    def __init__(self):
        self.clients: Dict[str, Set[WebSocketServerProtocol]] = {}
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True,
        )
        self.running = False
        self.loop = None

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        try:
            async for message in websocket:
                data = json.loads(message)
                action = data.get("action")
                stock_code = data.get("stock_code")

                if action == "subscribe" and stock_code:
                    if stock_code not in self.clients:
                        self.clients[stock_code] = set()
                    self.clients[stock_code].add(websocket)
                    await websocket.send(json.dumps({"status": "subscribed", "stock_code": stock_code}))
                    logger.info(f"Client subscribed to {stock_code}")

                elif action == "unsubscribe" and stock_code:
                    if stock_code in self.clients:
                        self.clients[stock_code].discard(websocket)
                        if not self.clients[stock_code]:
                            del self.clients[stock_code]
                    await websocket.send(json.dumps({"status": "unsubscribed", "stock_code": stock_code}))
                    logger.info(f"Client unsubscribed from {stock_code}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            for stock_code, clients in list(self.clients.items()):
                clients.discard(websocket)
                if not clients:
                    del self.clients[stock_code]

    async def broadcast_quotes(self):
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe("quote_stream")

        while self.running:
            try:
                message = pubsub.get_message(timeout=1)
                if message and message["type"] == "message":
                    quote_data = json.loads(message["data"])
                    stock_code = quote_data.get("stock_code")

                    if stock_code in self.clients:
                        disconnected = set()
                        for client in self.clients[stock_code]:
                            try:
                                await client.send(json.dumps(quote_data))
                            except:
                                disconnected.add(client)

                        for client in disconnected:
                            self.clients[stock_code].discard(client)

            except Exception as e:
                logger.error(f"Error broadcasting quotes: {e}")
                await asyncio.sleep(1)

    async def start_server(self, host: str, port: int):
        self.running = True
        async with websockets.serve(self.handle_client, host, port):
            logger.info(f"WebSocket server started on ws://{host}:{port}")
            await self.broadcast_quotes()

    def run(self, host: str = "0.0.0.0", port: int = 8765):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.start_server(host, port))

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.stop()


_ws_server = None
_ws_thread = None


def start_quote_websocket(host: str = "0.0.0.0", port: int = 8765):
    global _ws_server, _ws_thread
    if _ws_thread and _ws_thread.is_alive():
        return

    _ws_server = QuoteWebSocketServer()
    _ws_thread = threading.Thread(target=_ws_server.run, args=(host, port), daemon=True)
    _ws_thread.start()


def stop_quote_websocket():
    global _ws_server
    if _ws_server:
        _ws_server.stop()
