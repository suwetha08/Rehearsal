"""
test_step2_room_codes.py — Integration test for dynamic room code generation and usage.

Requirements:
1. Host creates a room with no code entered -> gets a valid 6-char code.
2. Participant tries to join with wrong code -> rejected (room_not_found).
3. Participant joins with correct code -> success.
4. Host disconnects and rejoins with same code -> reconnects to same room.
"""

import asyncio
import json
import os
import websockets

# Force fallback mode
os.environ.pop("GROQ_API_KEY", None)

async def main():
    print("\n[Step 2 Addendum] Dynamic Room Codes Test")
    print("=" * 64)

    # 1. Host creates a room (no code)
    print("Alice (Host) creates a new room (empty room_code)...")
    uri_alice = "ws://localhost:8000/ws/Alice?role=host&room_code="
    ws_alice = await websockets.connect(uri_alice)
    
    # Receive snapshot to find the room code
    msg1 = json.loads(await ws_alice.recv())
    room_code = msg1.get("room_id")
    
    if room_code and len(room_code) == 6:
        print(f"PASS: Valid room code generated -> {room_code}")
    else:
        print(f"FAIL: Invalid room code -> {room_code}")

    # Consume system/host update events
    await ws_alice.recv() # system
    await ws_alice.recv() # host update
    await ws_alice.recv() # snapshot

    # 2. Bob tries to join with a wrong code
    fake_code = "123456"
    print(f"\nBob (Participant) attempting to join with fake code {fake_code}...")
    uri_bob_wrong = f"ws://localhost:8000/ws/Bob?role=participant&room_code={fake_code}"
    try:
        ws_bob_fail = await websockets.connect(uri_bob_wrong)
        response = json.loads(await ws_bob_fail.recv())
        if response.get("reason") == "room_not_found":
            print(f"PASS: Bob rejected correctly -> {response}")
        else:
            print(f"FAIL: Bob got unexpected response -> {response}")
    except Exception as e:
        print(f"Connection failed directly: {e}")

    # 3. Bob joins with the correct code
    print(f"\nBob (Participant) attempting to join with valid code {room_code}...")
    uri_bob_correct = f"ws://localhost:8000/ws/Bob?role=participant&room_code={room_code}"
    ws_bob = await websockets.connect(uri_bob_correct)
    
    # Bob snapshot
    bob_snapshot = json.loads(await ws_bob.recv())
    if bob_snapshot.get("room_id") == room_code:
        print(f"PASS: Bob joined {room_code} successfully.")
    else:
        print("FAIL: Bob did not join the right room.")

    # 4. Host disconnects and reconnects with the same code
    print("\nAlice disconnects...")
    await ws_alice.close()
    
    # Give the backend a moment to process the disconnect
    await asyncio.sleep(0.5)

    print(f"Alice (Host) reconnects using specific code {room_code}...")
    uri_alice_reconnect = f"ws://localhost:8000/ws/Alice?role=host&room_code={room_code}"
    ws_alice2 = await websockets.connect(uri_alice_reconnect)
    
    alice_snapshot = json.loads(await ws_alice2.recv())
    
    if alice_snapshot.get("room_id") == room_code and "Bob" in alice_snapshot.get("connected_clients", []):
        print("PASS: Alice successfully reconnected to the existing room with Bob.")
    else:
        print("FAIL: Alice did not rejoin the expected room.")

    # Cleanup
    await ws_bob.close()
    await ws_alice2.close()
    
    print(f"\n{'='*64}")
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(main())
