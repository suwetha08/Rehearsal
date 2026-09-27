"""
test_e2e_3_rounds.py
"""
import asyncio
import json
import os
import websockets

os.environ.pop("GROQ_API_KEY", None)

async def flush_ws(ws):
    """Consume messages until a state_change is received."""
    while True:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            if msg.get("type") == "state_change":
                return msg
        except asyncio.TimeoutError:
            return None

async def wait_for_summary(ws):
    while True:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            if msg.get("type") == "state_change" and msg.get("state") == "round_summary":
                return msg
        except asyncio.TimeoutError:
            return None

async def wait_for_in_progress(ws):
    while True:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
            if msg.get("type") == "state_change" and msg.get("state") == "round_in_progress":
                return msg
        except asyncio.TimeoutError:
            return None

async def main():
    print("STEP 1: Host (Rahul) creates room")
    ws_rahul = await websockets.connect("ws://localhost:8000/ws/Rahul?role=host&room_code=")
    snap = json.loads(await ws_rahul.recv())
    room_code = snap["room_id"]
    print(f"Room Code: {room_code}")

    print("\nSTEP 2: Dave and Charlie join")
    ws_dave = await websockets.connect(f"ws://localhost:8000/ws/Dave?role=participant&room_code={room_code}")
    ws_charlie = await websockets.connect(f"ws://localhost:8000/ws/Charlie?role=participant&room_code={room_code}")
    await asyncio.sleep(1)

    # === ROUND 1 ===
    print("\nSTEP 3: Host starts session (Round 1)")
    await ws_rahul.send(json.dumps({"type": "advance_state"}))
    
    print("\nSTEP 4: Round 1 streams in")
    state_r1 = await wait_for_in_progress(ws_rahul)
    print(f"State: {state_r1['state']}, Question: {state_r1['current_question']}")
    
    print("\nSTEP 5: Submit answers")
    # Rahul (Fast + Thorough) -> Should score very high
    long_answer = "We need to immediately check the database CPU metrics and connection pools. If it is overloaded, we should spin up a read replica, redirect all read traffic, and aggressively cache the hot paths using Redis to shed load from the primary writer."
    await ws_rahul.send(json.dumps({"type": "chat", "message": long_answer}))
    
    await asyncio.sleep(1) # delay
    
    # Dave (Medium) -> Score medium
    await ws_dave.send(json.dumps({"type": "chat", "message": "I would check the application logs for any obvious errors or stack traces that point to the root cause of the outage."}))
    
    await asyncio.sleep(1) # delay
    
    # Charlie (Slow + Short) -> Score low
    await ws_charlie.send(json.dumps({"type": "chat", "message": "Restart everything."}))

    print("\nSTEP 6: Auto-advance (Round 1 Summary)")
    summary1 = await wait_for_summary(ws_rahul)
    print(f"Summary 1 Pressure: {summary1['panel_pressure_score']} | Tier: {summary1['difficulty']}")

    # === ROUND 2 ===
    print("\nSTEP 7: Round 2 question")
    await ws_rahul.send(json.dumps({"type": "advance_state"}))
    state_r2 = await wait_for_in_progress(ws_rahul)
    print(f"State: {state_r2['state']}, Question: {state_r2['current_question']}")
    
    # Answers (Everyone struggles this round)
    await asyncio.sleep(2)
    await ws_rahul.send(json.dumps({"type": "chat", "message": "I don't know."}))
    await asyncio.sleep(1)
    await ws_dave.send(json.dumps({"type": "chat", "message": "Not sure."}))
    await asyncio.sleep(1)
    await ws_charlie.send(json.dumps({"type": "chat", "message": "Pass."}))
    
    summary2 = await wait_for_summary(ws_rahul)
    print(f"Summary 2 Pressure: {summary2['panel_pressure_score']} | Tier: {summary2['difficulty']}")

    # === ROUND 3 ===
    print("\nSTEP 8: Round 3 pattern")
    await ws_rahul.send(json.dumps({"type": "advance_state"}))
    state_r3 = await wait_for_in_progress(ws_rahul)
    print(f"State: {state_r3['state']}, Question: {state_r3['current_question']}")
    
    # Answers (Everyone does amazingly)
    await ws_rahul.send(json.dumps({"type": "chat", "message": long_answer}))
    await ws_dave.send(json.dumps({"type": "chat", "message": long_answer}))
    await ws_charlie.send(json.dumps({"type": "chat", "message": long_answer}))
    
    summary3 = await wait_for_summary(ws_rahul)
    print(f"Summary 3 Pressure: {summary3['panel_pressure_score']} | Tier: {summary3['difficulty']}")

    await ws_rahul.close()
    await ws_dave.close()
    await ws_charlie.close()

if __name__ == "__main__":
    asyncio.run(main())
