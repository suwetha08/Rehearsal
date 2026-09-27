"""
test_step2_auto_advance.py — Verifies auto-advance logic for a 2-person room.

Requirements:
1. 2-person room (Alice = Host, Bob = Participant).
2. Alice starts the session.
3. Both answer.
4. The system automatically transitions to round_summary without an explicit advance_state call.
"""

import asyncio
import json
import os
import websockets

os.environ.pop("GROQ_API_KEY", None)

async def main():
    print("\n[Auto-Advance Bugfix] 2-Person Room Test")
    print("=" * 64)

    # 1. Connect Host
    print("Alice joins as Host...")
    uri_alice = "ws://localhost:8000/ws/Alice?role=host&room_code="
    ws_alice = await websockets.connect(uri_alice)
    
    # Extract code
    alice_snap = json.loads(await ws_alice.recv())
    room_code = alice_snap["room_id"]
    print(f"Room Code: {room_code}")
    await ws_alice.recv() # system
    await ws_alice.recv() # host update
    await ws_alice.recv() # snapshot
    
    # 2. Connect Participant
    print("Bob joins as Participant...")
    uri_bob = f"ws://localhost:8000/ws/Bob?role=participant&room_code={room_code}"
    ws_bob = await websockets.connect(uri_bob)
    
    await asyncio.sleep(0.5)
    
    # 3. Host starts session
    print("\nAlice starts the session (transitions to generating -> round_in_progress)...")
    await ws_alice.send(json.dumps({"type": "advance_state"}))
    await asyncio.sleep(2) # wait for generation
    
    # 4. Both answer
    print("\nAlice submits answer...")
    await ws_alice.send(json.dumps({"type": "chat", "message": "Alice answers."}))
    await asyncio.sleep(0.5)
    
    print("Bob submits answer...")
    await ws_bob.send(json.dumps({"type": "chat", "message": "Bob answers."}))
    
    # We DO NOT send `advance_state` from Alice here!
    # We just listen for state_change -> round_summary
    print("\nWaiting for auto-advance to round_summary...")
    
    success_summary = False
    new_difficulty = None
    try:
        while True:
            msg = json.loads(await asyncio.wait_for(ws_alice.recv(), timeout=5.0))
            if msg.get("type") == "state_change" and msg.get("state") == "round_summary":
                print(f"PASS: Round automatically advanced to round_summary!")
                print(f"Panel Pressure Score: {msg.get('panel_pressure_score')}")
                print(f"Responses this round: {msg.get('responses_this_round')}")
                new_difficulty = msg.get("difficulty")
                success_summary = True
                break
    except asyncio.TimeoutError:
        print("FAIL: Timed out waiting for auto-advance!")
        
    if success_summary:
        print("\nAlice (Host) advances to Round 2...")
        await ws_alice.send(json.dumps({"type": "advance_state"}))
        
        success_round_2 = False
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws_alice.recv(), timeout=5.0))
                if msg.get("type") == "question_complete" and msg.get("round") == 2:
                    print(f"PASS: Round 2 question successfully generated!")
                    print(f"Round 2 Difficulty Tier: {msg.get('difficulty')} (Previous was {new_difficulty})")
                    success_round_2 = True
                    break
        except asyncio.TimeoutError:
            print("FAIL: Timed out waiting for Round 2 generation!")
        
    await ws_alice.close()
    await ws_bob.close()
    
    print(f"\n{'='*64}")
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(main())
