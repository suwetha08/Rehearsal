"""
difficulty_engine.py — Adaptive Panel Pressure Score for Rehearsal.

Standalone module: no FastAPI, WebSocket, or Groq imports.
Can be imported, unit-tested, and demoed entirely independently.

─── Scoring model (v1) ───────────────────────────────────────────────────────

Per-answer score (0-100), two signals weighted 40/60:

  Latency signal (40%)
  ┌─────────────────────────────────────────────────────────────────┐
  │  0 – 15 s  : 70–80   (very fast; probably surface-level)       │
  │ 15 – 60 s  : 80–100  (sweet spot: quick but considered)        │
  │ 60 – 120 s : 60–80   (slower but acceptable)                   │
  │120 – 210 s : 25–60   (struggling)                              │
  │ > 210 s    : 10      (floor — really stuck)                    │
  └─────────────────────────────────────────────────────────────────┘

  Word-count signal (60%)
  ┌─────────────────────────────────────────────────────────────────┐
  │ < 20 words : 10–30   (single-sentence non-answer)              │
  │20 – 80     : 30–75   (brief but present)                       │
  │80 – 200    : 75–100  (solid medium answer)                     │
  │200 – 350   : 100     (comprehensive)                           │
  │ > 350 words: 90      (slight rambling penalty)                 │
  └─────────────────────────────────────────────────────────────────┘

Group aggregation (EMA)
  Round score = mean of all per-answer scores in that round.
  Panel Pressure Score = EMA across rounds:
      new_score = alpha * round_score + (1 - alpha) * prev_score
  Initial score = 55 (neutral / medium baseline).

Difficulty mapping
  score > 70  -> escalate one tier
  40 ≤ score ≤ 70 -> hold
  score < 40  -> de-escalate one tier
  Clamped: easy <= tier <= hard
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ── Tunable constants ────────────────────────────────────────────────────────
ALPHA: float = 0.4          # EMA recency weight (higher = more reactive)
INITIAL_SCORE: float = 55.0  # Neutral starting point → medium difficulty
ESCALATE_THRESHOLD: float = 70.0
DEESCALATE_THRESHOLD: float = 40.0

LATENCY_WEIGHT: float = 0.40
WORD_WEIGHT: float = 0.60

DIFFICULTY_ORDER = ("easy", "medium", "hard")


# ── Per-answer scoring ───────────────────────────────────────────────────────

def _latency_score(seconds: float) -> float:
    """
    Piecewise-linear latency -> 0-100 score.
    Sweet spot: 15-60s.  Floor: 10.
    """
    s = seconds
    if s < 0:
        s = 0
    if s <= 15:
        # Fast answers: 70 at 0s, ramps up to 80 at 15s
        return 70.0 + (s / 15.0) * 10.0
    elif s <= 60:
        # Sweet spot: 80 at 15s -> 100 at 60s
        return 80.0 + ((s - 15.0) / 45.0) * 20.0
    elif s <= 90:
        # Starting to slow: 100 at 60s -> 65 at 90s
        return 100.0 - ((s - 60.0) / 30.0) * 35.0
    elif s <= 150:
        # Struggling: 65 at 90s -> 25 at 150s
        return 65.0 - ((s - 90.0) / 60.0) * 40.0
    elif s <= 240:
        # Really stuck: 25 at 150s -> 10 at 240s
        return 25.0 - ((s - 150.0) / 90.0) * 15.0
    else:
        return 10.0


def _word_score(word_count: int) -> float:
    """Word count → 0-100 score proxy for answer depth."""
    w = max(0, word_count)
    if w < 20:
        return 10.0 + (w / 20.0) * 20.0        # 10 → 30
    elif w < 80:
        return 30.0 + ((w - 20) / 60.0) * 45.0  # 30 → 75
    elif w < 200:
        return 75.0 + ((w - 80) / 120.0) * 25.0 # 75 → 100
    elif w <= 350:
        return 100.0
    else:
        return 90.0  # slight rambling penalty


def score_answer(word_count: int, latency_seconds: float) -> float:
    """
    Compute a single answer's pressure score (0-100).

    Parameters
    ----------
    word_count       : number of words in the candidate's answer
    latency_seconds  : seconds between question appearing and answer submitted
    """
    lat = _latency_score(latency_seconds)
    wrd = _word_score(word_count)
    raw = LATENCY_WEIGHT * lat + WORD_WEIGHT * wrd
    return round(min(100.0, max(0.0, raw)), 2)


# ── Round & EMA aggregation ──────────────────────────────────────────────────

@dataclass
class RoundResult:
    """Summary of one completed round's group performance."""
    round_num: int
    answer_scores: list[float]          # one score per candidate
    round_score: float                  # mean of answer_scores
    panel_pressure_score: float         # EMA after this round
    previous_difficulty: str
    next_difficulty: str


@dataclass
class DifficultyEngine:
    """
    Stateful engine for one room.  Create one per room, keep it alive
    across rounds.

    Usage
    -----
    engine = DifficultyEngine(initial_difficulty="medium")

    # after each round:
    result = engine.record_round(
        round_num=1,
        answers=[{"word_count": 120, "latency_seconds": 45}, ...]
    )
    print(result.next_difficulty, result.panel_pressure_score)
    """
    initial_difficulty: str = "medium"
    alpha: float = ALPHA

    # mutable state (populated at runtime)
    panel_pressure_score: float = field(init=False)
    current_difficulty: str = field(init=False)
    round_history: list[RoundResult] = field(default_factory=list, init=False)

    def __post_init__(self):
        self.panel_pressure_score = INITIAL_SCORE
        self.current_difficulty = self.initial_difficulty

    # ── public API ───────────────────────────────────────────────────────────

    def record_round(
        self,
        round_num: int,
        answers: list[dict],
    ) -> RoundResult:
        """
        Process all answers from one completed round.

        Parameters
        ----------
        round_num : round index (1-based)
        answers   : list of dicts, each with keys:
                      word_count       (int)
                      latency_seconds  (float)

        Returns
        -------
        RoundResult with the new Panel Pressure Score and next difficulty tier.
        """
        if not answers:
            return self._no_change_result(round_num)

        # Score each answer
        per_scores = [
            score_answer(a["word_count"], a["latency_seconds"])
            for a in answers
        ]

        # Round score = group mean
        round_score = sum(per_scores) / len(per_scores)

        # EMA update
        prev_score = self.panel_pressure_score
        self.panel_pressure_score = (
            self.alpha * round_score + (1 - self.alpha) * prev_score
        )

        # Difficulty mapping
        prev_diff = self.current_difficulty
        self.current_difficulty = self._map_to_difficulty(self.panel_pressure_score)

        result = RoundResult(
            round_num=round_num,
            answer_scores=per_scores,
            round_score=round(round_score, 2),
            panel_pressure_score=round(self.panel_pressure_score, 2),
            previous_difficulty=prev_diff,
            next_difficulty=self.current_difficulty,
        )
        self.round_history.append(result)
        return result

    def snapshot(self) -> dict:
        """JSON-serialisable snapshot for WebSocket broadcast."""
        return {
            "panel_pressure_score": round(self.panel_pressure_score, 1),
            "difficulty": self.current_difficulty,
            "round_count": len(self.round_history),
        }

    # ── internals ────────────────────────────────────────────────────────────

    def _map_to_difficulty(self, score: float) -> str:
        idx = DIFFICULTY_ORDER.index(self.current_difficulty)
        if score > ESCALATE_THRESHOLD and idx < len(DIFFICULTY_ORDER) - 1:
            idx += 1
        elif score < DEESCALATE_THRESHOLD and idx > 0:
            idx -= 1
        return DIFFICULTY_ORDER[idx]

    def _no_change_result(self, round_num: int) -> RoundResult:
        return RoundResult(
            round_num=round_num,
            answer_scores=[],
            round_score=self.panel_pressure_score,
            panel_pressure_score=self.panel_pressure_score,
            previous_difficulty=self.current_difficulty,
            next_difficulty=self.current_difficulty,
        )
