"""
ai_generator.py — AI question generation for Rehearsal.

Streams questions token-by-token from Groq (primary) or Anthropic (secondary).
Falls back to the Step 3 static bank on any network/API failure so a demo
never silently breaks.

Public API
----------
async def stream_question(
    domain: str,
    difficulty: str,
    asked_questions: set[str],
) -> AsyncIterator[str]:
    Yields string tokens as they arrive from the LLM.
    On failure, yields the fallback question as a single token.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Optional

from dotenv import load_dotenv

from question_bank import get_next_question

load_dotenv()
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
GROQ_API_KEY: Optional[str] = os.environ.get("GROQ_API_KEY")
ANTHROPIC_API_KEY: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
AI_TIMEOUT: float = float(os.environ.get("AI_TIMEOUT", "12"))

DIFFICULTY_GUIDANCE = {
    "easy": (
        "conceptual understanding, basic definitions, or simple practical scenarios. "
        "A junior candidate with 0-1 year experience should be able to attempt this."
    ),
    "medium": (
        "design trade-offs, debugging scenarios, or moderate system/code reasoning. "
        "Expect a candidate with 2-4 years experience to answer well."
    ),
    "hard": (
        "deep system design, distributed systems edge-cases, or complex architectural "
        "decisions with real-world constraints. Senior/staff level expected."
    ),
}


def _build_system_prompt(domain: str, difficulty: str, asked_questions: set[str]) -> str:
    guidance = DIFFICULTY_GUIDANCE.get(difficulty, DIFFICULTY_GUIDANCE["medium"])
    asked_summary = ""
    if asked_questions:
        bullets = "\n".join(f"  - {q[:120]}" for q in list(asked_questions)[-6:])
        asked_summary = (
            f"\n\nQuestions already asked this session (DO NOT repeat or paraphrase these):\n"
            f"{bullets}"
        )

    return (
        f"You are an expert technical interviewer running a panel interview.\n"
        f"Domain: {domain}\n"
        f"Difficulty: {difficulty} — {guidance}\n"
        f"{asked_summary}\n\n"
        f"Generate exactly ONE interview question. Rules:\n"
        f"- No preamble, no numbering, no 'Here is your question:' opener\n"
        f"- No trailing explanation or expected-answer hints\n"
        f"- Match the difficulty tier described above precisely\n"
        f"- Keep it to 1-3 sentences maximum\n"
        f"- Output only the question text, ending with a question mark"
    )


# ── Groq streaming ─────────────────────────────────────────────────────────
async def _stream_groq(system_prompt: str) -> AsyncIterator[str]:
    from groq import AsyncGroq  # lazy import so missing package doesn't crash import

    client = AsyncGroq(api_key=GROQ_API_KEY)
    stream = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the next interview question."},
        ],
        stream=True,
        temperature=0.85,
        max_tokens=200,
    )
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


# ── Anthropic streaming ─────────────────────────────────────────────────────
async def _stream_anthropic(system_prompt: str) -> AsyncIterator[str]:
    import anthropic  # lazy import

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": "Generate the next interview question."}],
    ) as stream:
        async for token in stream.text_stream:
            yield token


# ── Fallback ────────────────────────────────────────────────────────────────
async def _fallback_question(
    domain: str, difficulty: str, asked_questions: set[str]
) -> AsyncIterator[str]:
    """Pull from static bank, simulating a single-token stream."""
    question = get_next_question(domain, difficulty, asked_questions)
    if question is None:
        # All static questions exhausted too — generate a generic one
        question = (
            f"Can you walk us through a challenging {domain} problem you have "
            f"solved at the {difficulty} level and explain your approach?"
        )
    logger.warning("[ai_generator] Using fallback static question: %s", question[:60])
    yield question


# ── Public entry point ───────────────────────────────────────────────────────
async def stream_question(
    domain: str,
    difficulty: str,
    asked_questions: set[str],
) -> AsyncIterator[str]:
    """
    Stream a generated question token-by-token.

    Priority:
      1. Groq  (if GROQ_API_KEY is set)
      2. Anthropic (if ANTHROPIC_API_KEY is set)
      3. Static bank fallback

    Any network/API error causes an immediate fallback with a warning log.
    """
    system_prompt = _build_system_prompt(domain, difficulty, asked_questions)

    # Pick provider
    if GROQ_API_KEY:
        provider_name = "Groq"
        stream_fn = lambda: _stream_groq(system_prompt)
    elif ANTHROPIC_API_KEY:
        provider_name = "Anthropic"
        stream_fn = lambda: _stream_anthropic(system_prompt)
    else:
        logger.warning("[ai_generator] No API key found. Using static fallback.")
        async for token in _fallback_question(domain, difficulty, asked_questions):
            yield token
        return

    logger.info("[ai_generator] Generating via %s (domain=%s, difficulty=%s)", provider_name, domain, difficulty)

    try:
        async def _collect_with_timeout():
            tokens = []
            async for token in stream_fn():
                tokens.append(token)
            return tokens

        tokens = await asyncio.wait_for(_collect_with_timeout(), timeout=AI_TIMEOUT)

        # Re-yield token by token (already buffered, preserves streaming illusion for the caller)
        for token in tokens:
            yield token

    except asyncio.TimeoutError:
        logger.error("[ai_generator] %s timed out after %ss — using fallback", provider_name, AI_TIMEOUT)
        async for token in _fallback_question(domain, difficulty, asked_questions):
            yield token
    except Exception as exc:
        logger.error("[ai_generator] %s error: %s — using fallback", provider_name, exc)
        async for token in _fallback_question(domain, difficulty, asked_questions):
            yield token
