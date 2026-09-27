from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List, Set, Any, Optional
import json
import logging
import asyncio
from enum import Enum
import time
import random

from dotenv import load_dotenv
from ai_generator import stream_question
from difficulty_engine import DifficultyEngine

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


class RoomState(str, Enum):
    WAITING_ROOM = "waiting_room"
    ROUND_IN_PROGRESS = "round_in_progress"
    ROUND_SUMMARY = "round_summary"
    GENERATING = "generating"   # transitional: AI is streaming the question


VALID_DOMAINS = {"backend", "frontend", "system_design"}
VALID_DIFFICULTIES = ("easy", "medium", "hard")


class Room:
    def __init__(self, room_id: str, domain: str = "backend", difficulty: str = "medium"):
        self.room_id = room_id
        self.domain = domain if domain in VALID_DOMAINS else "backend"
        self.difficulty = difficulty if difficulty in VALID_DIFFICULTIES else "medium"
        self.state = RoomState.WAITING_ROOM
        self.round = 0
        self.clients: Dict[str, WebSocket] = {}
        self.history: List[Dict[str, Any]] = []
        self.asked_questions: Set[str] = set()
        self.current_question: Optional[str] = None
        self.responses_this_round: Set[str] = set()
        self._generating: bool = False
        # Adaptive difficulty
        self.difficulty_engine = DifficultyEngine(initial_difficulty=self.difficulty)
        self.question_started_at: Optional[float] = None  # unix ts when question was broadcast
        self.panel_pressure_score: float = self.difficulty_engine.panel_pressure_score
        
        # Host tracking
        self.host_id: Optional[str] = None

    def add_client(self, client_id: str, websocket: WebSocket):
        self.clients[client_id] = websocket

    def remove_client(self, client_id: str):
        self.clients.pop(client_id, None)
        if self.host_id == client_id:
            self.host_id = None

    def snapshot(self) -> dict:
        return {
            "type": "state_change",
            "room_id": self.room_id,
            "state": self.state.value,
            "round": self.round,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "host_id": self.host_id,
            "panel_pressure_score": round(self.panel_pressure_score, 1),
            "current_question": self.current_question,
            "connected_clients": list(self.clients.keys()),
            "responses_this_round": list(self.responses_this_round),
            "asked_count": len(self.asked_questions),
        }

    def can_advance(self) -> bool:
        return (
            self.state in (RoomState.WAITING_ROOM, RoomState.ROUND_SUMMARY)
            and not self._generating
        )

    def advance_to_summary(self) -> bool:
        if self.state == RoomState.ROUND_IN_PROGRESS:
            self.state = RoomState.ROUND_SUMMARY
            return True
        return False

    def compute_round_pressure(self) -> Optional[dict]:
        """
        Score all answers from the most recent round via the difficulty engine.
        Returns the pressure_update payload or None if no answers this round.
        """
        # Gather answers from this round's history
        round_answers = [
            h for h in self.history if h["round"] == self.round
        ]
        if not round_answers:
            return None

        engine_answers = []
        for h in round_answers:
            word_count = len(h["answer"].split())
            # Latency: time from question shown to answer submitted
            if self.question_started_at:
                latency = max(0.0, h["timestamp"] - self.question_started_at)
            else:
                latency = 60.0  # neutral fallback
            engine_answers.append({"word_count": word_count, "latency_seconds": latency})

        result = self.difficulty_engine.record_round(self.round, engine_answers)

        # Sync room difficulty from engine
        self.difficulty = result.next_difficulty
        self.panel_pressure_score = result.panel_pressure_score

        return {
            "type": "pressure_update",
            "round": self.round,
            "answer_scores": result.answer_scores,
            "round_score": result.round_score,
            "panel_pressure_score": result.panel_pressure_score,
            "previous_difficulty": result.previous_difficulty,
            "next_difficulty": result.next_difficulty,
        }


class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def get_or_create_room(self, room_id: str, domain: str = "backend") -> Room:
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(room_id, domain=domain)
            logger.info(f"Created room '{room_id}' (domain={domain})")
        return self.rooms[room_id]

    async def connect(self, websocket: WebSocket, room_id: str, client_id: str, domain: str = "backend", role: str = "participant"):
        await websocket.accept()
        room = self.get_or_create_room(room_id, domain)
        
        if role == "host":
            if room.host_id is not None and room.host_id != client_id:
                await websocket.send_text(json.dumps({"type": "error", "reason": "host_taken"}))
                await websocket.close()
                return None
            room.host_id = client_id
            
        room.add_client(client_id, websocket)
        return room

    def disconnect(self, room_id: str, client_id: str):
        room = self.rooms.get(room_id)
        if room:
            room.remove_client(client_id)
            if not room.clients:
                del self.rooms[room_id]

    async def broadcast(self, payload: dict, room_id: str):
        room = self.rooms.get(room_id)
        if room:
            msg = json.dumps(payload)
            for ws in list(room.clients.values()):
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    async def start_round_with_ai(self, room: Room):
        """
        Generate the next question via AI (streaming), then start the round.
        Handles the GENERATING transitional state so clients see live tokens.
        """
        if not room.can_advance():
            return

        room._generating = True
        room.state = RoomState.GENERATING
        room.round += 1
        room.responses_this_round = set()
        room.current_question = None

        await self.broadcast(room.snapshot(), room.room_id)
        await self.broadcast(
            {"type": "question_stream_start", "round": room.round},
            room.room_id,
        )

        # Stream tokens, accumulating the full question
        accumulated = []
        try:
            async for token in stream_question(room.domain, room.difficulty, room.asked_questions):
                accumulated.append(token)
                await self.broadcast(
                    {"type": "question_token", "token": token, "round": room.round},
                    room.room_id,
                )
        except Exception as exc:
            logger.error("Error during question streaming: %s", exc)

        full_question = "".join(accumulated).strip()
        room.asked_questions.add(full_question)
        room.current_question = full_question
        room.state = RoomState.ROUND_IN_PROGRESS
        room._generating = False
        room.question_started_at = time.time()  # latency clock starts now
        
        logger.info(f"[{room.room_id}] State changed from GENERATING to ROUND_IN_PROGRESS")

        await self.broadcast(
            {
                "type": "question_complete",
                "round": room.round,
                "question": full_question,
                "domain": room.domain,
                "difficulty": room.difficulty,
            },
            room.room_id,
        )
        await self.broadcast(room.snapshot(), room.room_id)


manager = ConnectionManager()


def generate_room_code() -> str:
    # Uppercase alphanumeric, excluding 0, O, 1, I, L
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(chars, k=6))


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    room_code: str = "",
    domain: str = "backend",
    role: str = "participant",
):
    room_code = room_code.upper().strip()
    
    if role == "participant":
        if not room_code or room_code not in manager.rooms:
            await websocket.accept()
            await websocket.send_text(json.dumps({"type": "error", "reason": "room_not_found"}))
            await websocket.close()
            return
    elif role == "host":
        if not room_code:
            # Generate a new unique code
            while True:
                room_code = generate_room_code()
                if room_code not in manager.rooms:
                    break

    room = await manager.connect(websocket, room_code, client_id, domain, role)
    if room is None:
        return

    await websocket.send_text(json.dumps(room.snapshot()))
    await manager.broadcast(
        {"type": "system", "message": f"{client_id} joined", "client_id": client_id},
        room_code,
    )
    # Broadcast host update in case this client became the host
    await manager.broadcast({"type": "host_update", "host_id": room.host_id}, room_code)
    await manager.broadcast(room.snapshot(), room_code)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"type": "chat", "message": raw}

            msg_type = payload.get("type", "chat")

            # ── ADVANCE STATE ────────────────────────────────────────────
            if msg_type == "advance_state":
                if client_id != room.host_id:
                    await websocket.send_text(json.dumps({"type": "error", "reason": "host_only_action"}))
                    continue

                if room.state in (RoomState.WAITING_ROOM, RoomState.ROUND_SUMMARY):
                    # Fire AI generation in background so this coroutine stays responsive
                    logger.info(f"[{room_code}] State changed from {room.state.value} to {RoomState.GENERATING.value}")
                    asyncio.create_task(manager.start_round_with_ai(room))

                elif room.state == RoomState.ROUND_IN_PROGRESS:
                    if len(room.responses_this_round) < len(room.clients):
                        missing = len(room.clients) - len(room.responses_this_round)
                        total = len(room.clients)
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "reason": "incomplete_responses",
                            "message": f"Cannot advance: {missing} of {total} participants have not answered yet."
                        }))
                        continue

                    if room.advance_to_summary():
                        # Run difficulty engine and broadcast pressure update
                        pressure = room.compute_round_pressure()
                        if pressure:
                            await manager.broadcast(pressure, room_code)
                        await manager.broadcast(room.snapshot(), room_code)

            # ── CHAT / ANSWER ────────────────────────────────────────────
            elif msg_type == "chat":
                answer_text = payload.get("message", "")
                if room.state == RoomState.ROUND_IN_PROGRESS:
                    room.responses_this_round.add(client_id)
                    room.history.append(
                        {
                            "round": room.round,
                            "question": room.current_question,
                            "respondent": client_id,
                            "answer": answer_text,
                            "timestamp": time.time(),
                        }
                    )
                    logger.info(f"[{room_code}] Answer received from {client_id}. Total responses: {len(room.responses_this_round)} / {len(room.clients)}")
                    
                await manager.broadcast(
                    {"type": "chat", "client_id": client_id, "message": answer_text},
                    room_code,
                )
                
                # Check auto-advance
                if room.state == RoomState.ROUND_IN_PROGRESS and len(room.responses_this_round) >= len(room.clients):
                    logger.info(f"[{room_code}] All participants answered. Auto-advancing to ROUND_SUMMARY.")
                    if room.advance_to_summary():
                        logger.info(f"[{room_code}] State changed from ROUND_IN_PROGRESS to ROUND_SUMMARY")
                        pressure = room.compute_round_pressure()
                        if pressure:
                            await manager.broadcast(pressure, room_code)
                
                await manager.broadcast(room.snapshot(), room_code)

    except WebSocketDisconnect:
        manager.disconnect(room_code, client_id)
        if room_code in manager.rooms:
            room = manager.rooms[room_code]
            await manager.broadcast(
                {"type": "system", "message": f"{client_id} left", "client_id": client_id},
                room_code,
            )
            await manager.broadcast({"type": "host_update", "host_id": room.host_id}, room_code)
            await manager.broadcast(room.snapshot(), room_code)
