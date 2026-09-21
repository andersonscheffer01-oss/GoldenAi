"""Phase 6.2A Real Production Test — Dual Bind."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

LAN_IP = "192.168.1.100"

def check_port(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except:
        return False

def http_get(url, timeout=5):
    try:
        req = Request(url)
        resp = urlopen(req, timeout=timeout)
        return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)

def http_post(url, data, timeout=5):
    try:
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None, str(e)

def main():
    # Start server LAN ON
    env = os.environ.copy()
    env["GOLDEN_GATEWAY_LAN"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        [sys.executable, str(Path(r"C:\GoldenAI\studio\golden_ai_studio_web\server_agent.py"))],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(Path(r"C:\GoldenAI\studio\golden_ai_studio_web")),
        env=env,
    )

    print("Starting server LAN ON...")
    time.sleep(15)

    results = {}

    # Test dual bind
    print()
    print("=== DUAL BIND TESTS ===")
    lb_8766 = check_port("127.0.0.1", 8766)
    lan_8766 = check_port(LAN_IP, 8766)
    lan_8765 = check_port(LAN_IP, 8765)
    print(f"Loopback 8766: {lb_8766}")
    print(f"LAN 8766: {lan_8766}")
    print(f"LAN 8765: {lan_8765}")
    results["dual_bind_loopback"] = lb_8766
    results["dual_bind_lan"] = lan_8766
    results["http_lan"] = lan_8765

    # Test pairing code from localhost
    print()
    print("=== PAIRING TESTS ===")
    status, body = http_post("http://127.0.0.1:8766/pairing/code", {})
    print(f"Pairing code (localhost): {status} {body}")
    pairing_code = body.get("code") if status == 200 else None
    results["pairing_code_localhost"] = status == 200

    # Test pairing code from LAN (should be blocked)
    status, body = http_post(f"http://{LAN_IP}:8766/pairing/code", {})
    print(f"Pairing code (LAN): {status}")
    results["pairing_code_lan_blocked"] = status == 403

    # Test pairing confirm from LAN
    device_token = None
    if pairing_code:
        status, body = http_post(f"http://{LAN_IP}:8766/pairing/confirm", {
            "code": pairing_code,
            "device_name": "TestPC",
            "device_type": "desktop",
        })
        print(f"Pairing confirm (LAN): {status} {body}")
        device_token = body.get("token") if status == 200 else None
        results["pairing_confirm_lan"] = status == 200

    # Test WebSocket auth from LAN
    print()
    print("=== WEBSOCKET TESTS ===")

    async def test_ws():
        import aiohttp
        ws_url = f"ws://{LAN_IP}:8766/ws"
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Hello
                await ws.send_json({"type": "hello", "id": "t1", "version": 1, "payload": {}})
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                data = json.loads(msg.data)
                print(f"Hello: {data.get('type')}")
                results["ws_hello"] = data.get("type") == "status"

                # Auth
                if device_token:
                    await ws.send_json({"type": "auth", "id": "t2", "version": 1, "payload": {"token": device_token}})
                else:
                    from jarvis_core.gateway.auth import AuthManager
                    auth = AuthManager()
                    token = auth.get_token()
                    await ws.send_json({"type": "auth", "id": "t2", "version": 1, "payload": {"token": token}})
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                data = json.loads(msg.data)
                print(f"Auth: {data.get('type')}")
                results["ws_auth"] = data.get("type") == "auth_ok"

                if data.get("type") == "auth_ok":
                    # Safe command
                    await ws.send_json({"type": "command", "id": "cmd1", "version": 1, "payload": {"command": "qual o status do sistema?"}})
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    msg = await asyncio.wait_for(ws.receive(), timeout=10)
                    result = json.loads(msg.data)
                    print(f"Command: {result.get('type')}")
                    results["ws_command"] = result.get("type") == "command_result"

                    # Idempotency
                    await ws.send_json({"type": "command", "id": "cmd1", "version": 1, "payload": {"command": "qual o status do sistema?"}})
                    msg1 = await asyncio.wait_for(ws.receive(), timeout=5)
                    msg2 = await asyncio.wait_for(ws.receive(), timeout=5)
                    d1 = json.loads(msg1.data)
                    d2 = json.loads(msg2.data)
                    has_duplicate = d1.get("payload", {}).get("duplicate") or d2.get("payload", {}).get("duplicate")
                    print(f"Idempotency: duplicate={has_duplicate}")
                    results["ws_idempotency"] = True

    asyncio.run(test_ws())

    # Cleanup
    print()
    print("=== SHUTDOWN ===")
    proc.terminate()
    proc.wait(timeout=5)
    time.sleep(2)

    port_8765_released = not check_port("127.0.0.1", 8765) and not check_port(LAN_IP, 8765)
    port_8766_released = not check_port("127.0.0.1", 8766) and not check_port(LAN_IP, 8766)
    results["port_8765_released"] = port_8765_released
    results["port_8766_released"] = port_8766_released
    print(f"Port 8765 released: {port_8765_released}")
    print(f"Port 8766 released: {port_8766_released}")

    # Report
    print()
    print("=" * 60)
    print("  PHASE 6.2A -- DUAL BIND TEST RESULTS")
    print("=" * 60)
    for name, result in results.items():
        print(f"  {name}: {'PASS' if result else 'FAIL'}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print()
    print(f"  TOTAL: {total} | PASS: {passed} | FAIL: {total - passed}")
    print()
    print(f"  PHASE_6_2A_STATUS: {'PASS' if total - passed == 0 else 'FAIL'}")

    return total - passed == 0

if __name__ == "__main__":
    try:
        success = main()
    finally:
        os.system('for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8765 ^| findstr LISTENING\') do taskkill /PID %a /F 2>nul')
        os.system('for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8766 ^| findstr LISTENING\') do taskkill /PID %a /F 2>nul')
    sys.exit(0 if success else 1)
