"""Test WebSocket quote subscription."""

import json
import time
import redis
from threading import Thread
import websocket


def test_websocket():
    """Test WebSocket subscription."""
    print("Testing WebSocket...")

    messages = []

    def on_message(ws, message):
        print(f"Received: {message}")
        messages.append(message)

    def on_error(ws, error):
        print(f"Error: {error}")

    def on_close(ws, close_status_code, close_msg):
        print("Connection closed")

    def on_open(ws):
        print("Connected to WebSocket")
        # Subscribe to stock
        ws.send(json.dumps({"action": "subscribe", "stock_code": "000001"}))
        time.sleep(1)
        ws.send(json.dumps({"action": "subscribe", "stock_code": "600000"}))

    ws = websocket.WebSocketApp(
        "ws://127.0.0.1:8080/ws",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    # Run WebSocket in thread
    ws_thread = Thread(target=ws.run_forever, daemon=True)
    ws_thread.start()

    time.sleep(2)

    # Publish test quote to Redis
    print("\nPublishing test quotes to Redis...")
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    for i in range(3):
        quote = {
            "stock_code": "000001",
            "price": 10.50 + i * 0.1,
            "volume": 1000 + i * 100,
            "timestamp": time.time()
        }
        r.publish("quote_stream", json.dumps(quote))
        print(f"Published: {quote}")
        time.sleep(1)

    time.sleep(2)

    # Unsubscribe
    print("\nUnsubscribing from 000001...")
    ws.send(json.dumps({"action": "unsubscribe", "stock_code": "000001"}))
    time.sleep(1)

    ws.close()
    print(f"\nTotal messages received: {len(messages)}")


if __name__ == "__main__":
    from src.infrastructure.runtime.cms_server import start_cms_server, stop_cms_server

    print("Starting server...")
    start_cms_server("127.0.0.1", 8080)
    time.sleep(2)

    try:
        test_websocket()
    finally:
        print("\nStopping server...")
        stop_cms_server()
        print("Done!")
