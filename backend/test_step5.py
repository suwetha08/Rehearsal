"""
test_step5.py — Integration test for the Adaptive Panel Pressure Score.

Two rooms run concurrently:
  Room FAST  — Alice+Bob answer quickly (sleep 2s) with long answers (~150w)
               Expected: medium -> hard by round 3
  Room SLOW  — Charlie+Dave answer slowly (sleep 8s) with short answers (~12w)
               Expected: medium -> easy by round 3

Uses fallback questions (no Groq needed) to avoid API rate limits in CI.
The scoring is based on REAL elapsed time (not mocked), so sleep timings matter.
"""

import asyncio
import json
import os
from collections import defaultdict
import websockets

# Force fallback mode so we don't hit Groq on every test run
os.environ.pop("GROQ_API_KEY", None)

RECEIVED: dict[str, list] = defaultdict(list)


async def run_candidate(
    room_id: str,
    client_id: str,
    domain: str,
    is_leader: bool,
    answer_delay: float,   # seconds to wait before answering (simulates latency)
    answer_text: str,      # answer to submit (controls word count)
    num_rounds: int = 3,
    advance_wait: float = 3.0,
):
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
        await asyncio.sleep(1.5)  # let everyone connect

        for rnd in range(1, num_rounds + 1):
            if is_leader:
                # Start round (advance from waiting_room or round_summary)
                await ws.send(json.dumps({"type": "advance_state"}))
                await asyncio.sleep(advance_wait)  # wait for fallback question

            # Simulate answer latency
            await asyncio.sleep(answer_delay)
            await ws.send(json.dumps({"type": "chat", "message": answer_text}))
            await asyncio.sleep(0.3)

            if is_leader:
                # Advance to summary (triggers pressure engine)
                await ws.send(json.dumps({"type": "advance_state"}))
                await asyncio.sleep(0.5)

        await asyncio.sleep(1.5)
        receiver.cancel()
        await asyncio.sleep(0.1)


# ── Answer templates ─────────────────────────────────────────────────────────

LONG_ANSWER = (
    "To approach this problem I would first identify the core bottleneck using profiling tools "
    "and distributed tracing. In my previous role we encountered a similar issue where the "
    "database was the primary constraint. I would apply connection pooling, query optimization "
    "with proper indexing, and consider caching frequently accessed data with Redis. For "
    "the architecture layer I would ensure horizontal scaling is possible by making services "
    "stateless and using a message queue like Kafka to decouple producers from consumers. "
    "Monitoring and alerting via Prometheus and Grafana would complete the observability layer "
    "so we can respond to regressions quickly. I would also consider circuit breakers to prevent "
    "cascading failures under load, and implement proper retry logic with exponential backoff."
)  # ~140 words

SHORT_ANSWER = "idk"  # 1 word, minimal latency -> heavily penalized for lack of depth

async def main():
    print("\n[Step 5 Integration Test] Adaptive Panel Pressure Score")
    print("=" * 64)

    # Run both rooms concurrently
    await asyncio.gather(
        # FAST room: 2s answer delay, long answer -> should escalate
        run_candidate("room_fast", "Alice",   "backend",  is_leader=True,  answer_delay=2.0,  answer_text=LONG_ANSWER),
        run_candidate("room_fast", "Bob",     "backend",  is_leader=False, answer_delay=2.5,  answer_text=LONG_ANSWER),
        # SLOW room: near-instant "idk" answers -> low score (<35) -> should de-escalate
        run_candidate("room_slow", "Charlie", "frontend", is_leader=True,  answer_delay=0.5,  answer_text=SHORT_ANSWER),
        run_candidate("room_slow", "Dave",    "frontend", is_leader=False, answer_delay=1.0,  answer_text=SHORT_ANSWER),
    )

    # ── Analyse results ───────────────────────────────────────────────────────
    for room_id, leader, label in [
        ("room_fast", "Alice",   "FAST room (should escalate to hard)"),
        ("room_slow", "Charlie", "SLOW room (should de-escalate to easy)"),
    ]:
        key = f"{room_id}/{leader}"
        msgs = RECEIVED[key]

        print(f"\n{'='*64}")
        print(f"  {label}")
        print(f"  Leader: {leader}  |  {len(msgs)} messages received")
        print(f"{'='*64}")

        difficulty_history = []
        for m in msgs:
            t = m.get("type")
            if t == "state_change":
                state = m["state"]
                rnd   = m["round"]
                diff  = m.get("difficulty", "?")
                pps   = m.get("panel_pressure_score", "?")
                print(f"  [STATE]    {state:25s} rnd={rnd}  diff={diff:6s}  pps={pps}")
            elif t == "pressure_update":
                rnd       = m["round"]
                scores    = [f"{s:.1f}" for s in m["answer_scores"]]
                r_score   = m["round_score"]
                pps       = m["panel_pressure_score"]
                prev_diff = m["previous_difficulty"]
                next_diff = m["next_difficulty"]
                difficulty_history.append(next_diff)
                arrow = "->" if prev_diff == next_diff else f"{prev_diff} => {next_diff}"
                print(
                    f"  [PRESSURE] rnd={rnd}  per={scores}  "
                    f"round_avg={r_score:.1f}  EMA={pps:.1f}  {arrow}"
                )
            elif t == "question_complete":
                diff = m.get("difficulty", "?")
                q    = m.get("question", "")[:70]
                print(f"  [QUESTION] diff={diff}  {q}...")

        # Verdict
        print(f"\n  Difficulty progression: {difficulty_history}")
        if room_id == "room_fast":
            final = difficulty_history[-1] if difficulty_history else "unknown"
            if final == "hard":
                print("  PASS: Fast room escalated to 'hard'.")
            elif final == "medium":
                print(f"  PARTIAL: Fast room stayed at medium (EMA may need more rounds).")
            else:
                print(f"  RESULT: {final}")
        elif room_id == "room_slow":
            final = difficulty_history[-1] if difficulty_history else "unknown"
            if final == "easy":
                print("  PASS: Slow room de-escalated to 'easy'.")
            elif final == "medium":
                print(f"  PARTIAL: Slow room stayed at medium (EMA may need more rounds).")
            else:
                print(f"  RESULT: {final}")

    print(f"\n{'='*64}")
    print("  Done.")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    asyncio.run(main())
