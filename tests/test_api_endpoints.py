"""Test API endpoints and WebSocket functionality."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.healthcheck import start_healthcheck_server, stop_healthcheck_server


def test_http_endpoints():
    """Test HTTP API endpoints."""
    print("Testing HTTP endpoints...")

    base_url = "http://127.0.0.1:8080"
    session = requests.Session()
    session.trust_env = False

    # Test health endpoint
    print("\n1. Testing /health endpoint...")
    try:
        resp = session.get(f"{base_url}/health", timeout=5)
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")

    # Test positions endpoint
    print("\n2. Testing /api/positions endpoint...")
    try:
        resp = session.get(f"{base_url}/api/positions", timeout=5)
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")

    # Test orders endpoint with pagination
    print("\n3. Testing /api/orders endpoint (page=1, limit=10)...")
    try:
        resp = session.get(f"{base_url}/api/orders?page=1&limit=10", timeout=5)
        print(f"   Status: {resp.status_code}")
        data = resp.json()
        print(f"   Total: {data.get('total')}, Page: {data.get('page')}, Limit: {data.get('limit')}")
        print(f"   Data count: {len(data.get('data', []))}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test signals endpoint
    print("\n4. Testing /api/signals endpoint...")
    try:
        resp = session.get(f"{base_url}/api/signals?page=1&limit=5", timeout=5)
        print(f"   Status: {resp.status_code}")
        data = resp.json()
        print(f"   Total: {data.get('total')}, Data count: {len(data.get('data', []))}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test trades endpoint
    print("\n5. Testing /api/trades endpoint...")
    try:
        resp = session.get(f"{base_url}/api/trades?page=1&limit=5", timeout=5)
        print(f"   Status: {resp.status_code}")
        data = resp.json()
        print(f"   Total: {data.get('total')}, Data count: {len(data.get('data', []))}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test PnL endpoint
    print("\n6. Testing /api/pnl endpoint...")
    try:
        resp = session.get(f"{base_url}/api/pnl", timeout=5)
        print(f"   Status: {resp.status_code}")
        data = resp.json()
        print(f"   PnL data count: {len(data)}")
    except Exception as e:
        print(f"   Error: {e}")


if __name__ == "__main__":
    print("Starting health check server...")
    start_healthcheck_server("127.0.0.1", 8080)
    time.sleep(2)

    try:
        test_http_endpoints()
    finally:
        print("\n\nStopping server...")
        stop_healthcheck_server()
        print("Done!")
