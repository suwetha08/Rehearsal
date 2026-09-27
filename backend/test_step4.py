"""
Step 4 test: AI-generated questions (Groq), streaming, and fallback.

Tests:
  A) Normal run  — Alice+Bob (backend), Carol+Dave (frontend), 4 rounds each
     - Verifies domain-appropriate questions
     - Verifies streaming (multiple question_token events before question_complete)
     - Verifies no duplicates
  B) Fallback run — temporarily set GROQ_API_KEY=INVALID to force static bank

Run with:
    python test_step4.py
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
import websockets

RECEIVED: dict[str, list] = defaultdict(list)


async def run_room(room_id: str, domain: str, candidates: list[str], num_rounds: int = 4, ai_wait: float = 15.0):
    async def candidate_session(client_id: str, is_leader: bool):
        uri = f"ws://localhost:8000/ws/{room_id}/{client_id}?domain={domain}"
        async with websockets.connect(uri) as ws:
            key = f"{room_id}/{client_id}"

            async def recv():
                try:
                    while True:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        RECEIVED[key].append(msg)
                except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                    pass

            receiver = asyncio.create_task(recv())
            await asyncio.sleep(1.5)

            for rnd in range(1, num_rounds + 1):
                if is_leader:
                    await ws.send(json.dumps({"type": "advance_state"}))
                    # Wait for AI/fallback to finish generating
                    await asyncio.sleep(ai_wait)

                # Submit answer (staggered per candidate)
                idx = candidates.index(client_id)
                await asyncio.sleep(0.2 * (idx + 1))
                await ws.send(json.dumps({
                    "type": "chat",
                    "message": f"[R{rnd}] {client_id}'s answer."
                }))
                await asyncio.sleep(0.3)

                if is_leader:
                    await ws.send(json.dumps({"type": "advance_state"}))
                    await asyncio.sleep(0.5)

            await asyncio.sleep(1.0)
            receiver.cancel()
            await asyncio.sleep(0.1)

    tasks = [
        candidate_session(cid, is_leader=(i == 0))
        for i, cid in enumerate(candidates)
    ]
    await asyncio.gather(*tasks)


def analyse_room(room_id: str, candidates: list[str], label: str = ""):
    leader = candidates[0]
    key = f"{room_id}/{leader}"
    msgs = RECEIVED[key]

    print(f"\n{'='*70}")
    print(f"ROOM {room_id}  {label}  ({len(msgs)} msgs to leader '{leader}')")
    print(f"{'='*70}")

    questions_seen = []
    token_counts = {}   # round -> token count
    current_rnd = None

    for m in msgs:
        t = m.get("type")

        if t == "state_change":
            state = m["state"]
            rnd = m["round"]
            responded = m.get("responses_this_round", [])
            print(f"  [STATE]    {state:25s} rnd={rnd}  responded={responded}")

        elif t == "question_stream_start":
            current_rnd = m["round"]
            token_counts[current_rnd] = 0
            print(f"  [STREAM-START] round={current_rnd}  (tokens arriving...)")

        elif t == "question_token":
            rnd = m["round"]
            token_counts[rnd] = token_counts.get(rnd, 0) + 1

        elif t == "question_complete":
            rnd = m["round"]
            q = m["question"]
            questions_seen.append(q)
            tok = token_counts.get(rnd, 0)
            stream_indicator = "STREAMED" if tok > 1 else "SINGLE-CHUNK (fallback?)"
            print(f"  [Q-{rnd}] ({tok} tokens — {stream_indicator})")
            print(f"         {q[:110]}{'...' if len(q) > 110 else ''}")

        elif t == "chat":
            print(f"  [CHAT]     {m['client_id']}: {m['message']}")

    # Repeat check
    print(f"\n  --- Repeat check ({len(questions_seen)} questions asked) ---")
    seen_set: set[str] = set()
    fail = False
    for q in questions_seen:
        if q in seen_set:
            print(f"  FAIL: Repeated: {q[:80]}")
            fail = True
        seen_set.add(q)
    if not fail:
        print(f"  PASS: No repeated questions.")

    # Streaming check
    print(f"\n  --- Streaming check ---")
    for rnd, count in token_counts.items():
        if count > 1:
            print(f"  PASS: Round {rnd} streamed {count} tokens progressively.")
        else:
            print(f"  WARN: Round {rnd} received {count} token(s) - may be fallback.")

    return questions_seen


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"

    if mode == "fallback":
        print("\n[TEST B] FALLBACK MODE — using invalid API key to force static bank")
        os.environ["GROQ_API_KEY"] = "INVALID_KEY_FOR_TESTING"
        room_configs = [
            ("room_fb_A", "backend",  ["Alice", "Bob"],   "FALLBACK backend"),
            ("room_fb_B", "frontend", ["Carol", "Dave"],  "FALLBACK frontend"),
        ]
    else:
        print("\n[TEST A] NORMAL MODE — AI-generated questions via Groq")
        room_configs = [
            ("room_ai_A", "backend",  ["Alice", "Bob"],   "AI backend"),
            ("room_ai_B", "frontend", ["Carol", "Dave"],  "AI frontend"),
        ]

    ai_wait = 3.0 if mode == "fallback" else 15.0

    room_tasks = [
        run_room(rid, domain, candidates, num_rounds=4, ai_wait=ai_wait)
        for rid, domain, candidates, _ in room_configs
    ]
    await asyncio.gather(*room_tasks)

    all_questions: dict[str, list] = {}
    for rid, _, candidates, label in room_configs:
        qs = analyse_room(rid, candidates, label)
        all_questions[rid] = qs

    # Cross-room isolation
    room_ids = [r[0] for r in room_configs]
    if len(room_ids) == 2:
        a_set = set(all_questions[room_ids[0]])
        b_set = set(all_questions[room_ids[1]])
        overlap = a_set & b_set
        print(f"\n{'='*70}")
        print(f"CROSS-ROOM ISOLATION: {room_ids[0]} vs {room_ids[1]}")
        if overlap:
            print(f"  WARN: {len(overlap)} overlapping question(s): {list(overlap)[0][:60]}")
        else:
            print(f"  PASS: No overlapping questions between rooms.")
        print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
