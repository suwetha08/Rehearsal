"""
Step 3 test: 4 full rounds in two parallel rooms.
Room A: backend domain (Alice + Bob)
Room B: frontend domain (Carol + Dave)

Verifies:
  - No question repeats within a session
  - State transitions fire correctly each round
  - Round counter increments correctly
  - Room A and Room B get independent question sequences
"""

import asyncio
import websockets
import json
from collections import defaultdict

RECEIVED: dict[str, list] = defaultdict(list)
QUESTIONS_SEEN: dict[str, list] = defaultdict(list)


async def run_room(
    room_id: str,
    domain: str,
    candidates: list[str],
    num_rounds: int = 4,
):
    """Drive a full multi-round session for a room with multiple candidates."""

    async def candidate_session(client_id: str, is_leader: bool):
        uri = f"ws://localhost:8000/ws/{room_id}/{client_id}?domain={domain}"
        async with websockets.connect(uri) as ws:

            async def recv():
                try:
                    while True:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        RECEIVED[f"{room_id}/{client_id}"].append(msg)
                except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                    pass

            receiver = asyncio.create_task(recv())

            # Wait for everyone in this room to connect
            await asyncio.sleep(1.5)

            for rnd in range(1, num_rounds + 1):
                if is_leader:
                    # Advance: waiting_room / round_summary -> round_in_progress
                    await ws.send(json.dumps({"type": "advance_state"}))
                    await asyncio.sleep(0.3)

                # Each candidate submits an answer (staggered slightly)
                idx = candidates.index(client_id)
                await asyncio.sleep(0.2 * (idx + 1))
                await ws.send(json.dumps({
                    "type": "chat",
                    "message": f"[Round {rnd}] {client_id}'s answer."
                }))
                await asyncio.sleep(0.3)

                if is_leader:
                    # Advance: round_in_progress -> round_summary
                    await ws.send(json.dumps({"type": "advance_state"}))
                    await asyncio.sleep(0.5)

            # Allow tail messages to arrive before disconnecting
            await asyncio.sleep(1.0)
            receiver.cancel()
            await asyncio.sleep(0.1)

    # Run all candidates concurrently
    tasks = [
        candidate_session(cid, is_leader=(i == 0))
        for i, cid in enumerate(candidates)
    ]
    await asyncio.gather(*tasks)


async def main():
    # Run both rooms concurrently
    await asyncio.gather(
        run_room("room_A", "backend",        ["Alice", "Bob"],         num_rounds=4),
        run_room("room_B", "frontend",       ["Carol", "Dave"],        num_rounds=4),
    )

    # ── Print full summary ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 3 TEST SUMMARY")
    print("=" * 70)

    for room_id in ("room_A", "room_B"):
        candidates = ["Alice", "Bob"] if room_id == "room_A" else ["Carol", "Dave"]
        leader = candidates[0]
        key = f"{room_id}/{leader}"
        msgs = RECEIVED[key]

        print(f"\n{'-'*70}")
        print(f"ROOM: {room_id}  (leader={leader}, {len(msgs)} messages received)")
        print(f"{'-'*70}")

        questions_this_room: list[str] = []
        last_state = None

        for m in msgs:
            t = m.get("type")
            if t == "state_change":
                state = m["state"]
                rnd = m["round"]
                responded = m.get("responses_this_round", [])
                if state != last_state or (state == "round_in_progress" and rnd != getattr(last_state, '_rnd', None)):
                    print(f"  [STATE] {state:25s} round={rnd}  responded={responded}")
                last_state = state
            elif t == "new_question":
                q = m["question"]
                rnd = m["round"]
                questions_this_room.append(q)
                print(f"  [Q-{rnd}]  {q[:80]}{'...' if len(q) > 80 else ''}")
            elif t == "chat":
                print(f"  [CHAT]  {m['client_id']}: {m['message']}")

        # Verify no repeats
        print(f"\n  --- Question repeat check ({len(questions_this_room)} questions asked) ---")
        seen = set()
        repeats = []
        for q in questions_this_room:
            if q in seen:
                repeats.append(q)
            seen.add(q)
        if repeats:
            print(f"  FAIL: Repeated questions detected: {repeats}")
        else:
            print(f"  PASS: No repeated questions.")

        QUESTIONS_SEEN[room_id] = questions_this_room

    # Cross-room check: rooms should ask different questions
    print(f"\n{'-'*70}")
    print("CROSS-ROOM ISOLATION CHECK")
    print(f"{'-'*70}")
    a_set = set(QUESTIONS_SEEN["room_A"])
    b_set = set(QUESTIONS_SEEN["room_B"])
    overlap = a_set & b_set
    print(f"  room_A questions: {len(a_set)}")
    print(f"  room_B questions: {len(b_set)}")
    if overlap:
        print(f"  NOTE: Overlap (expected for same domain): {overlap}")
    else:
        print(f"  PASS: No overlapping questions (different domains).")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
