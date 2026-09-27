"""
test_step2_parallel_answers.py — Integration test for parallel answering and host blocking.

Requirements:
1. Create a room with Host (Alice) + 3 participants (Bob, Charlie, Dave).
2. Alice answers Round 1.
3. Alice attempts to advance early -> gets blocked.
4. Bob, Charlie, Dave answer Round 1.
5. Alice attempts to advance -> succeeds.
"""

import asyncio
import json
import os
import websockets

os.environ.pop("GROQ_API_KEY", None)

async def main():
    print("\n[Step 2 Addendum] Parallel Answers & Host Blocking Test")
    print("=" * 64)

    # 1. Connect Host
    print("Alice joins as Host...")
    uri_alice = "ws://localhost:8000/ws/Alice?role=host&room_code="
    ws_alice = await websockets.connect(uri_alice)
    
    # Snapshot -> extract code
    alice_snap = json.loads(await ws_alice.recv())
    room_code = alice_snap["room_id"]
    print(f"Room Code: {room_code}")

    await ws_alice.recv() # system
    await ws_alice.recv() # host update
    await ws_alice.recv() # snapshot
    
    # Connect Participants
    print("Bob, Charlie, Dave join as Participants...")
    uris = [f"ws://localhost:8000/ws/{name}?role=participant&room_code={room_code}" for name in ["Bob", "Charlie", "Dave"]]
    ws_bob = await websockets.connect(uris[0])
    ws_charlie = await websockets.connect(uris[1])
    ws_dave = await websockets.connect(uris[2])
    
    # Wait a bit for joins to settle
    await asyncio.sleep(1)
    
    # Host starts the session
    print("\nAlice starts the session...")
    await ws_alice.send(json.dumps({"type": "advance_state"}))
    await asyncio.sleep(1.5) # Wait for round generation

    # 2. Alice answers
    print("\nAlice submits an answer...")
    await ws_alice.send(json.dumps({"type": "chat", "message": "Alice answer"}))
    await asyncio.sleep(0.5)

    # 3. Alice attempts early advance
    print("Alice attempts to force advance early...")
    await ws_alice.send(json.dumps({"type": "advance_state"}))
    
    # Read Alice's messages to look for error
    error_found = False
    try:
        while True:
            msg = json.loads(await asyncio.wait_for(ws_alice.recv(), timeout=0.5))
            if msg.get("type") == "error" and msg.get("reason") == "incomplete_responses":
                print(f"PASS: Advance blocked properly -> {msg['message']}")
                error_found = True
                break
    except asyncio.TimeoutError:
        pass
    
    if not error_found:
        print("FAIL: Did not receive incomplete_responses error!")

    # 4. Bob, Charlie, Dave answer
    print("\nBob, Charlie, Dave submit answers...")
    await ws_bob.send(json.dumps({"type": "chat", "message": "Bob answer"}))
    await ws_charlie.send(json.dumps({"type": "chat", "message": "Charlie answer"}))
    await ws_dave.send(json.dumps({"type": "chat", "message": "Dave answer"}))
    
    await asyncio.sleep(0.5)

    # 5. Alice attempts advance -> succeeds
    print("Alice attempts to force advance again...")
    await ws_alice.send(json.dumps({"type": "advance_state"}))
    
    success = False
    try:
        while True:
            msg = json.loads(await asyncio.wait_for(ws_alice.recv(), timeout=5.0))
            if msg.get("type") == "state_change" and msg.get("state") == "round_summary":
                print(f"PASS: Round advanced successfully to round_summary. Score: {msg.get('panel_pressure_score')}")
                success = True
                break
    except asyncio.TimeoutError:
        print("DEBUG: Timeout waiting for state_change")
        
    if not success:
        print("FAIL: Did not transition to round_summary!")
        
    # Cleanup
    await ws_alice.close()
    await ws_bob.close()
    await ws_charlie.close()
    await ws_dave.close()

    print(f"\n{'='*64}")
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(main())
