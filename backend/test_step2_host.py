"""
test_step2_host.py — Integration test for Host Tracking functionality.

Requirements:
1. Connect Alice, Bob, Carol. Alice is host.
2. Bob attempts `advance_state` -> rejected with `host_only_action`.
3. Alice attempts `advance_state` -> succeeds (starts AI round).
4. Alice disconnects -> Bob promoted to host, receives `host_update`.
"""

import asyncio
import json
import os
import websockets
from collections import defaultdict

# Force fallback mode to avoid Groq latency/limits during host testing
os.environ.pop("GROQ_API_KEY", None)

ROOM_ID = "host_test_room"
RECEIVED = defaultdict(list)

async def connect_and_listen(client_id: str, cancel_event: asyncio.Event):
    uri = f"ws://localhost:8000/ws/{ROOM_ID}/{client_id}?domain=backend"
    try:
        async with websockets.connect(uri) as ws:
            print(f"[{client_id}] Connected.")
            
            # The test will orchestrate via global tasks or waits.
            # We'll just read incoming messages and store them.
            
            while not cancel_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    msg = json.loads(raw)
                    RECEIVED[client_id].append(msg)
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break
    except Exception as e:
        print(f"[{client_id}] Error: {e}")

async def send_cmd(client_id: str, payload: dict):
    uri = f"ws://localhost:8000/ws/{ROOM_ID}/{client_id}?domain=backend"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(payload))
        # Wait a tiny bit for the server to process
        await asyncio.sleep(0.5)
        # We don't read back here; the listener tasks will catch the broadcasts.

async def single_command_and_close(client_id: str, payload: dict):
    # Some actions we just want to send and close, like when testing rejection.
    uri = f"ws://localhost:8000/ws/{ROOM_ID}/{client_id}?domain=backend"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(payload))
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            return json.loads(raw)
        except:
            return None

async def main():
    print("\n[Step 2 Addendum] Host Tracking Test")
    print("=" * 64)

    cancel_bob = asyncio.Event()
    cancel_carol = asyncio.Event()

    # 1. Connect Alice (will be host), Bob, Carol in sequence.
    # We will connect Alice, then Bob, then Carol to ensure strict ordering.
    
    # Actually, we can use single persistent connections if we manage them in the script.
    
    uri_alice = f"ws://localhost:8000/ws/{ROOM_ID}/Alice"
    uri_bob = f"ws://localhost:8000/ws/{ROOM_ID}/Bob"
    uri_carol = f"ws://localhost:8000/ws/{ROOM_ID}/Carol"

    ws_alice = await websockets.connect(uri_alice)
    ws_bob = await websockets.connect(uri_bob)
    ws_carol = await websockets.connect(uri_carol)
    
    print("Alice, Bob, and Carol connected in sequence.")
    await asyncio.sleep(0.5)

    async def listen(ws, name):
        try:
            while True:
                msg = json.loads(await ws.recv())
                RECEIVED[name].append(msg)
        except websockets.exceptions.ConnectionClosed:
            pass

    task_alice = asyncio.create_task(listen(ws_alice, "Alice"))
    task_bob = asyncio.create_task(listen(ws_bob, "Bob"))
    task_carol = asyncio.create_task(listen(ws_carol, "Carol"))
    
    await asyncio.sleep(1.0) # Let them receive initial snapshot & host_update

    print("\n[Test 1] Confirm Alice is host in snapshots...")
    for msg in RECEIVED["Carol"]:
        if msg.get("type") == "state_change" and msg.get("host_id"):
            print(f"Carol sees host: {msg['host_id']}")
            break

    print("\n[Test 2] Bob attempts to start session (advance_state)...")
    await ws_bob.send(json.dumps({"type": "advance_state"}))
    await asyncio.sleep(1.0)
    
    bob_errors = [m for m in RECEIVED["Bob"] if m.get("type") == "error"]
    if bob_errors:
        print(f"PASS: Bob received error -> {bob_errors[0]}")
    else:
        print("FAIL: Bob did not receive an error.")

    print("\n[Test 3] Alice attempts to start session...")
    await ws_alice.send(json.dumps({"type": "advance_state"}))
    await asyncio.sleep(2.0) # Wait for fallback AI generation
    
    alice_state_changes = [m for m in RECEIVED["Alice"] if m.get("type") == "state_change"]
    started = any(m.get("state") == "round_in_progress" for m in alice_state_changes)
    if started:
        print("PASS: Alice successfully advanced the state to round_in_progress.")
    else:
        print("FAIL: Alice could not advance the state.")

    print("\n[Test 4] Alice disconnects mid-session...")
    await ws_alice.close()
    await asyncio.sleep(1.0) # Wait for server to promote Bob and broadcast

    bob_host_updates = [m for m in RECEIVED["Bob"] if m.get("type") == "host_update"]
    carol_host_updates = [m for m in RECEIVED["Carol"] if m.get("type") == "host_update"]
    
    print(f"Bob received host updates: {[m['host_id'] for m in bob_host_updates]}")
    print(f"Carol received host updates: {[m['host_id'] for m in carol_host_updates]}")
    
    if bob_host_updates and bob_host_updates[-1]["host_id"] == "Bob":
        print("PASS: Bob was successfully promoted to host.")
    else:
        print("FAIL: Bob was not promoted to host.")

    # Cleanup
    await ws_bob.close()
    await ws_carol.close()
    task_alice.cancel()
    task_bob.cancel()
    task_carol.cancel()
    
    print(f"\n{'='*64}")
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(main())
