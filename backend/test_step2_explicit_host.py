"""
test_step2_explicit_host.py — Integration test for Explicit Host Tracking.

Requirements:
1. Join as Alice (host) — confirm she gets host controls.
2. Attempt to join as Bob (host) in the same room — confirm rejection (host_taken).
3. Join Bob as participant instead — confirm success.
4. Disconnect Alice — confirm Bob does NOT get auto-promoted.
5. Have a new user, Carol, join as host — confirm she becomes the new host.
"""

import asyncio
import json
import os
import websockets
from collections import defaultdict

# Force fallback mode
os.environ.pop("GROQ_API_KEY", None)

ROOM_ID = "explicit_host_test_room"
RECEIVED = defaultdict(list)

async def listen(ws, name):
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            msg = json.loads(raw)
            RECEIVED[name].append(msg)
    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
        pass

async def main():
    print("\n[Step 2 Addendum] Explicit Host Tracking Test")
    print("=" * 64)

    # 1. Join Alice (host)
    uri_alice = f"ws://localhost:8000/ws/{ROOM_ID}/Alice?role=host"
    ws_alice = await websockets.connect(uri_alice)
    print("Alice joined as host.")
    
    # Wait for snapshot
    msg = json.loads(await ws_alice.recv())
    if msg.get("host_id") == "Alice":
        print("PASS: Alice is confirmed as host.")
    else:
        print("FAIL: Alice is not host in snapshot.")

    # 2. Bob joins as host
    uri_bob_host = f"ws://localhost:8000/ws/{ROOM_ID}/Bob?role=host"
    print("\nBob attempting to join as host...")
    try:
        ws_bob_fail = await websockets.connect(uri_bob_host)
        response = json.loads(await ws_bob_fail.recv())
        if response.get("reason") == "host_taken":
            print(f"PASS: Bob rejected correctly -> {response}")
        else:
            print(f"FAIL: Bob got unexpected response -> {response}")
    except Exception as e:
        print(f"Connection failed directly: {e}")

    # 3. Bob joins as participant
    uri_bob_part = f"ws://localhost:8000/ws/{ROOM_ID}/Bob?role=participant"
    print("\nBob attempting to join as participant...")
    ws_bob = await websockets.connect(uri_bob_part)
    
    # discard Bob's initial snapshot and system messages
    await ws_bob.recv() # snapshot
    await ws_bob.recv() # system (joined)
    await ws_bob.recv() # host_update
    await ws_bob.recv() # snapshot
    
    print("PASS: Bob joined successfully as participant.")

    # 4. Disconnect Alice
    print("\nDisconnecting Alice...")
    await ws_alice.close()
    
    # Wait to see what Bob receives
    await asyncio.sleep(1.0)
    
    bob_host_updates = []
    try:
        while True:
            raw = await asyncio.wait_for(ws_bob.recv(), timeout=0.5)
            data = json.loads(raw)
            if data.get("type") == "host_update":
                bob_host_updates.append(data)
    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
        pass

    if bob_host_updates and bob_host_updates[-1].get("host_id") is None:
        print("PASS: Alice left, Bob was NOT auto-promoted (host is None).")
    else:
        print(f"FAIL: Expected host=None, got {bob_host_updates}")

    # 5. Carol joins as Host
    print("\nCarol attempting to join as host...")
    uri_carol = f"ws://localhost:8000/ws/{ROOM_ID}/Carol?role=host"
    ws_carol = await websockets.connect(uri_carol)
    
    msg = json.loads(await ws_carol.recv())
    if msg.get("host_id") == "Carol":
        print("PASS: Carol is confirmed as the new host.")
    else:
        print("FAIL: Carol is not host in snapshot.")

    # Cleanup
    await ws_bob.close()
    await ws_carol.close()
    
    print(f"\n{'='*64}")
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(main())
