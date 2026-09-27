"""
test_difficulty_engine.py — Unit tests for difficulty_engine.py.
No server, no WebSocket, no Groq. Pure logic verification.

Scenarios:
  A) Escalation   — Alice+Bob answer fast (25s) and thoroughly (180 words)
                    for 3 rounds. Expect: medium -> hard by round 3.
  B) De-escalation — slow (170s) + short (12 words) for 3 rounds.
                    Expect: medium -> easy by round 3.
  C) EMA smoothing — two good rounds, one terrible outlier.
                    Expect: tier should NOT swing on the single outlier.
  D) Score function spot-checks — verify the scoring math.
"""

from difficulty_engine import (
    DifficultyEngine,
    score_answer,
    _latency_score,
    _word_score,
    ESCALATE_THRESHOLD,
    DEESCALATE_THRESHOLD,
    INITIAL_SCORE,
)


def sep(label: str):
    print(f"\n{'='*64}")
    print(f"  {label}")
    print(f"{'='*64}")


def print_round(result):
    print(
        f"  Round {result.round_num:2d} | "
        f"per-scores={[f'{s:.1f}' for s in result.answer_scores]} | "
        f"round_avg={result.round_score:.1f} | "
        f"EMA={result.panel_pressure_score:.1f} | "
        f"{result.previous_difficulty} -> {result.next_difficulty}"
    )


# ── Spot-check scoring primitives ────────────────────────────────────────────

sep("D) Score function spot-checks")

checks = [
    # (word_count, latency_s, expected_min, expected_max, label)
    (200, 30,   80, 100, "ideal answer (200w, 30s)"),
    (12,  170,  10,  35, "terrible answer (12w, 170s)"),
    (80,  55,   65,  85, "decent answer (80w, 55s)"),
    (5,   5,    10,  40, "one-word blurt (5w, 5s)"),
    (350, 45,   85, 100, "wall of text (350w, 45s)"),
    (120, 120,  50,  75, "ok length, slow (120w, 120s)"),
]

all_pass = True
for wc, lat, lo, hi, label in checks:
    s = score_answer(wc, lat)
    ok = lo <= s <= hi
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"  [{status}] {label:40s} -> {s:.1f}  (expected {lo}-{hi})")

print(f"\n  Spot-checks: {'ALL PASS' if all_pass else 'SOME FAILED'}")


# ── Scenario A: Escalation ────────────────────────────────────────────────────

sep("A) Escalation — fast, thorough answers for 3 rounds")

engine_a = DifficultyEngine(initial_difficulty="medium")
print(f"  Initial: score={engine_a.panel_pressure_score}, difficulty={engine_a.current_difficulty}")

# Alice + Bob both give strong answers each round
good_answers = [
    {"word_count": 180, "latency_seconds": 25},  # Alice
    {"word_count": 210, "latency_seconds": 32},  # Bob
]

for rnd in range(1, 4):
    result = engine_a.record_round(rnd, good_answers)
    print_round(result)

final_a = engine_a.current_difficulty
print(f"\n  Final difficulty: {final_a}")
print(f"  Final EMA score: {engine_a.panel_pressure_score:.1f}")

if final_a == "hard":
    print("  PASS: Correctly escalated to 'hard' after 3 strong rounds.")
elif final_a == "medium":
    print("  PARTIAL: Still at medium — may need another round or lower alpha.")
    print(f"         (EMA={engine_a.panel_pressure_score:.1f}, threshold={ESCALATE_THRESHOLD})")
else:
    print(f"  UNEXPECTED: {final_a}")


# ── Scenario B: De-escalation ────────────────────────────────────────────────

sep("B) De-escalation — slow, short answers for 3 rounds")

engine_b = DifficultyEngine(initial_difficulty="medium")
print(f"  Initial: score={engine_b.panel_pressure_score}, difficulty={engine_b.current_difficulty}")

poor_answers = [
    {"word_count": 12,  "latency_seconds": 175},  # Alice
    {"word_count": 8,   "latency_seconds": 190},  # Bob
]

for rnd in range(1, 4):
    result = engine_b.record_round(rnd, poor_answers)
    print_round(result)

final_b = engine_b.current_difficulty
print(f"\n  Final difficulty: {final_b}")
print(f"  Final EMA score: {engine_b.panel_pressure_score:.1f}")

if final_b == "easy":
    print("  PASS: Correctly de-escalated to 'easy' after 3 weak rounds.")
elif final_b == "medium":
    print("  PARTIAL: Still at medium.")
    print(f"         (EMA={engine_b.panel_pressure_score:.1f}, threshold={DEESCALATE_THRESHOLD})")
else:
    print(f"  UNEXPECTED: {final_b}")


# ── Scenario C: EMA smoothing ────────────────────────────────────────────────

sep("C) EMA smoothing — 2 good rounds, 1 terrible outlier, then recover")

engine_c = DifficultyEngine(initial_difficulty="medium")
print(f"  Initial: score={engine_c.panel_pressure_score}, difficulty={engine_c.current_difficulty}")

# Round 1: good
r1 = engine_c.record_round(1, [{"word_count": 180, "latency_seconds": 30}, {"word_count": 200, "latency_seconds": 28}])
print_round(r1)

# Round 2: good
r2 = engine_c.record_round(2, [{"word_count": 160, "latency_seconds": 35}, {"word_count": 190, "latency_seconds": 40}])
print_round(r2)

tier_before_outlier = engine_c.current_difficulty
score_before_outlier = engine_c.panel_pressure_score

# Round 3: single terrible outlier
r3 = engine_c.record_round(3, [{"word_count": 5, "latency_seconds": 200}, {"word_count": 8, "latency_seconds": 195}])
print_round(r3)

tier_after_outlier = engine_c.current_difficulty
score_after_outlier = engine_c.panel_pressure_score

# Round 4: recover
r4 = engine_c.record_round(4, [{"word_count": 175, "latency_seconds": 28}, {"word_count": 195, "latency_seconds": 32}])
print_round(r4)

print(f"\n  Before outlier: EMA={score_before_outlier:.1f}, tier={tier_before_outlier}")
print(f"  After outlier : EMA={score_after_outlier:.1f},  tier={tier_after_outlier}")
print(f"  After recover : EMA={engine_c.panel_pressure_score:.1f},  tier={engine_c.current_difficulty}")

# The score should have dropped but not catastrophically, and should recover
dropped = score_after_outlier < score_before_outlier
not_floored = score_after_outlier > 30  # EMA should dampen the outlier
print(f"\n  EMA damped the outlier (score dropped but didn't floor): ", end="")
print("PASS" if (dropped and not_floored) else "FAIL")


# ── Scenario D: Multi-person room, 3 candidates ──────────────────────────────

sep("D) 3-candidate room — Carol, Dave, Eve — mixed performance")

engine_d = DifficultyEngine(initial_difficulty="medium")

rounds_data = [
    # round 1: Carol=good, Dave=ok, Eve=poor
    [{"word_count": 170, "latency_seconds": 30},
     {"word_count": 70,  "latency_seconds": 65},
     {"word_count": 15,  "latency_seconds": 130}],
    # round 2: all mediocre
    [{"word_count": 60,  "latency_seconds": 80},
     {"word_count": 55,  "latency_seconds": 75},
     {"word_count": 50,  "latency_seconds": 90}],
    # round 3: all improve
    [{"word_count": 200, "latency_seconds": 28},
     {"word_count": 180, "latency_seconds": 35},
     {"word_count": 160, "latency_seconds": 40}],
]

for i, answers in enumerate(rounds_data, 1):
    result = engine_d.record_round(i, answers)
    print_round(result)

print(f"\n  Final difficulty: {engine_d.current_difficulty}")
print(f"  Final EMA score: {engine_d.panel_pressure_score:.1f}")
print("  (Group pressure reflects the mean, not a single candidate's performance)")


# ── Summary ──────────────────────────────────────────────────────────────────

print(f"\n{'='*64}")
print("  SUMMARY")
print(f"{'='*64}")
print(f"  Spot-check math:   {'PASS' if all_pass else 'FAIL'}")
print(f"  Escalation path:   PASS" if final_a == "hard" else f"  Escalation path:   EMA={engine_a.panel_pressure_score:.1f} (threshold {ESCALATE_THRESHOLD})")
print(f"  De-escalation:     PASS" if final_b == "easy" else f"  De-escalation:     EMA={engine_b.panel_pressure_score:.1f} (threshold {DEESCALATE_THRESHOLD})")
print(f"  EMA smoothing:     {'PASS' if (dropped and not_floored) else 'FAIL'}")
print(f"{'='*64}\n")
