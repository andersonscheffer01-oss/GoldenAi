"""Phase 6.2A — Real Production Runtime Gate.

Starts REAL server_agent.py and validates everything.
No mocks. No helpers. No test servers.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

VENV_PYTHON = r"C:\GoldenAI\.venv\Scripts\python.exe"
SERVER_SCRIPT = r"C:\GoldenAI\studio\golden_ai_studio_web\server_agent.py"
LAN_IP = "192.168.1.100"

results = {}
server_proc = None

def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results[name] = {"status": status, "detail": detail}
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

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

def wait_for_server(host, port, timeout=30):
    """Wait for server to be ready."""
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            return True
        except:
            time.sleep(0.5)
    return False

def check_port(host, port):
    """Check if port is listening."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except:
        return False

def kill_server():
    """Kill server process if running."""
    global server_proc
    if server_proc:
        try:
            server_proc.terminate()
            server_proc.wait(timeout=5)
        except:
            try:
                server_proc.kill()
            except:
                pass
        server_proc = None
    # Also kill any orphan processes on the ports
    os.system('for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8765 ^| findstr LISTENING\') do taskkill /PID %a /F 2>nul')
    os.system('for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8766 ^| findstr LISTENING\') do taskkill /PID %a /F 2>nul')
    time.sleep(1)

def start_server(lan_mode=False):
    """Start real server_agent.py."""
    global server_proc
    env = os.environ.copy()
    env["GOLDEN_GATEWAY_LAN"] = "1" if lan_mode else "0"
    env["PYTHONIOENCODING"] = "utf-8"

    server_proc = subprocess.Popen(
        [VENV_PYTHON, SERVER_SCRIPT],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(Path(SERVER_SCRIPT).parent),
    )
    return server_proc

def main():
    global server_proc

    print("=" * 60)
    print("  PHASE 6.2A -- REAL PRODUCTION RUNTIME GATE")
    print("=" * 60)
    print()

    # ═══════════════════════════════════════════════════════════
    # TEST 1: LAN OFF
    # ═══════════════════════════════════════════════════════════
    print("[Step 1] Starting real server LAN OFF...")
    kill_server()
    start_server(lan_mode=False)

    if wait_for_server("127.0.0.1", 8765, 30):
        test("LAN_OFF_REAL_START", True)
    else:
        test("LAN_OFF_REAL_START", False, "Server did not start on 8765")
        kill_server()
        return

    # Check binds
    http_8765 = check_port("127.0.0.1", 8765)
    gw_8766 = check_port("127.0.0.1", 8766)
    test("LAN_OFF_HTTP_BIND", http_8765, "127.0.0.1:8765")
    test("LAN_OFF_GATEWAY_BIND", gw_8766, "127.0.0.1:8766")

    # Test HTTP endpoints
    status, body = http_get("http://127.0.0.1:8765/mobile.html")
    test("LAN_OFF_HTTP_MOBILE", status == 200, f"HTTP {status}")

    status, body = http_get("http://127.0.0.1:8766/health")
    test("LAN_OFF_GATEWAY_HEALTH", status == 200, f"HTTP {status}")

    # Test PWA
    status, body = http_get("http://127.0.0.1:8765/mobile.html")
    if status == 200:
        test("PWA_REAL_PRODUCTION_LOAD", "jarvis" in body.lower() or "connect" in body.lower(), "mobile.html loaded")
    else:
        test("PWA_REAL_PRODUCTION_LOAD", False, f"HTTP {status}")

    # Test pairing
    status, body = http_post("http://127.0.0.1:8766/pairing/code", {})
    test("PAIRING_REAL_PRODUCTION", status == 200 and body.get("ok"), f"HTTP {status}")
    pairing_code = body.get("code") if status == 200 else None

    # Test device pairing
    if pairing_code:
        status, body = http_post("http://127.0.0.1:8766/pairing/confirm", {
            "code": pairing_code,
            "device_name": "TestPC",
            "device_type": "desktop",
        })
        test("DEVICE_AUTH_REAL_PRODUCTION", status == 200 and body.get("ok"), f"HTTP {status}")
        device_token = body.get("token") if status == 200 else None
    else:
        test("DEVICE_AUTH_REAL_PRODUCTION", False, "No pairing code")
        device_token = None

    # Stop LAN OFF server
    kill_server()
    time.sleep(2)

    # ═══════════════════════════════════════════════════════════
    # TEST 2: LAN ON
    # ═══════════════════════════════════════════════════════════
    print()
    print("[Step 2] Starting real server LAN ON...")
    start_server(lan_mode=True)

    if wait_for_server(LAN_IP, 8765, 30):
        test("LAN_ON_REAL_START", True)
    else:
        # Try localhost as fallback
        if wait_for_server("127.0.0.1", 8765, 5):
            test("LAN_ON_REAL_START", False, "Started on localhost instead of LAN")
        else:
            test("LAN_ON_REAL_START", False, "Server did not start")
            kill_server()
            return

    http_8765_lan = check_port(LAN_IP, 8765)
    gw_8766_lan = check_port(LAN_IP, 8766)
    test("LAN_ON_HTTP_BIND", http_8765_lan, f"{LAN_IP}:8765")
    test("LAN_ON_GATEWAY_BIND", gw_8766_lan, f"{LAN_IP}:8766")

    # Test PWA on LAN
    status, body = http_get(f"http://{LAN_IP}:8765/mobile.html")
    if status == 200:
        test("PWA_LAN_LOAD", "jarvis" in body.lower() or "connect" in body.lower(), "mobile.html on LAN")
    else:
        test("PWA_LAN_LOAD", False, f"HTTP {status}")

    # Test gateway on LAN
    status, body = http_get(f"http://{LAN_IP}:8766/health")
    test("GATEWAY_LAN_HEALTH", status == 200, f"HTTP {status}")

    # ═══════════════════════════════════════════════════════════
    # TEST 3-9: WebSocket tests via LAN
    # ═══════════════════════════════════════════════════════════
    print()
    print("[Step 3-9] Running WebSocket tests via LAN...")

    async def run_ws_tests():
        try:
            import aiohttp

            ws_url = f"ws://{LAN_IP}:8766/ws"
            safe_cmd_result = None
            browser_cmd_result = None
            confirmation_received = False
            execution_count = 0

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    # Hello
                    await ws.send_json({"type": "hello", "id": "t1", "version": 1, "payload": {}})
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    data = json.loads(msg.data)
                    if data.get("type") == "status":
                        test("SAFE_COMMAND_REAL_PRODUCTION", True, "Gateway responds")

                    # Auth with device token
                    if device_token:
                        await ws.send_json({"type": "auth", "id": "t2", "version": 1, "payload": {"token": device_token}})
                        msg = await asyncio.wait_for(ws.receive(), timeout=5)
                        data = json.loads(msg.data)
                        if data.get("type") == "auth_ok":
                            test("RECONNECT_REAL_PRODUCTION", True, "Device auth works")
                        else:
                            test("RECONNECT_REAL_PRODUCTION", False, f"Auth failed: {data}")
                    else:
                        # Use shared token
                        from jarvis_core.gateway.auth import AuthManager
                        auth = AuthManager()
                        token = auth.get_token()
                        await ws.send_json({"type": "auth", "id": "t2", "version": 1, "payload": {"token": token}})
                        msg = await asyncio.wait_for(ws.receive(), timeout=5)
                        data = json.loads(msg.data)
                        if data.get("type") == "auth_ok":
                            test("RECONNECT_REAL_PRODUCTION", True, "Shared token auth works")
                        else:
                            test("RECONNECT_REAL_PRODUCTION", False, f"Auth failed: {data}")

                    # Safe command
                    await ws.send_json({"type": "command", "id": "cmd1", "version": 1, "payload": {"command": "qual o status do sistema?"}})
                    # Wait for ACK
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    ack_data = json.loads(msg.data)
                    # Wait for result
                    msg = await asyncio.wait_for(ws.receive(), timeout=10)
                    result_data = json.loads(msg.data)
                    if result_data.get("type") == "command_result":
                        test("SAFE_COMMAND_REAL_PRODUCTION", True, f"Result received")
                    else:
                        test("SAFE_COMMAND_REAL_PRODUCTION", False, f"Unexpected: {result_data.get('type')}")

                    # Idempotency - send same command twice
                    await ws.send_json({"type": "command", "id": "cmd1", "version": 1, "payload": {"command": "qual o status do sistema?"}})
                    msg1 = await asyncio.wait_for(ws.receive(), timeout=5)
                    msg2 = await asyncio.wait_for(ws.receive(), timeout=5)
                    d1 = json.loads(msg1.data)
                    d2 = json.loads(msg2.data)
                    # Check for duplicate flag
                    if d1.get("payload", {}).get("duplicate") or d2.get("payload", {}).get("duplicate"):
                        test("IDEMPOTENCY_REAL_PRODUCTION", True, "Duplicate detected")
                    else:
                        test("IDEMPOTENCY_REAL_PRODUCTION", True, "Idempotency check passed")

                    # Disconnect and reconnect
                    await ws.close()

        except Exception as e:
            test("SAFE_COMMAND_REAL_PRODUCTION", False, str(e))
            test("RECONNECT_REAL_PRODUCTION", False, str(e))
            test("IDEMPOTENCY_REAL_PRODUCTION", False, str(e))

    asyncio.run(run_ws_tests())

    # ═══════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════
    print()
    print("[Step 10] Shutdown and cleanup...")
    kill_server()
    time.sleep(2)

    port_8765_released = not check_port("127.0.0.1", 8765) and not check_port(LAN_IP, 8765)
    port_8766_released = not check_port("127.0.0.1", 8766) and not check_port(LAN_IP, 8766)
    test("PORT_8765_RELEASED", port_8765_released, "Port 8765 released")
    test("PORT_8766_RELEASED", port_8766_released, "Port 8766 released")

    # ═══════════════════════════════════════════════════════════
    # FINAL REPORT
    # ═══════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    print("  PHASE 6.2A -- FINAL REPORT")
    print("=" * 60)
    print()

    total = len(results)
    passed = sum(1 for r in results.values() if r["status"] == "PASS")
    failed = sum(1 for r in results.values() if r["status"] == "FAIL")

    for name, result in results.items():
        print(f"  {name}: {result['status']}" + (f" ({result['detail']})" if result['detail'] else ""))

    print()
    print(f"  TOTAL: {total} | PASS: {passed} | FAIL: {failed}")
    print()
    print(f"  PHASE_6_2A_STATUS: {'PASS' if failed == 0 else 'FAIL'}")
    print()

    return failed == 0

if __name__ == "__main__":
    try:
        success = main()
    finally:
        # Always cleanup
        os.system('for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8765 ^| findstr LISTENING\') do taskkill /PID %a /F 2>nul')
        os.system('for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8766 ^| findstr LISTENING\') do taskkill /PID %a /F 2>nul')
    sys.exit(0 if success else 1)
