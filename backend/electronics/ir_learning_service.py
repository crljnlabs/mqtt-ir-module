import re
import threading
import time
from typing import Any, Dict, List, Optional

from agents.agent_registry import AgentRegistry
from database import Database

from .ir_hold_extractor import IrHoldExtractor
from .ir_signal_aggregator import IrSignalAggregator
from .ir_signal_parser import IrSignalParser
from .models import LearningSession, LogEntry
from .status_communication import StatusCommunication


class IrLearningService:
    def __init__(
        self,
        database: Database,
        agent_registry: AgentRegistry,
        parser: IrSignalParser,
        aggregator: IrSignalAggregator,
        hold_extractor: IrHoldExtractor,
        debug: bool,
        aggregate_round_to_us: int,
        aggregate_min_match_ratio: float,
        hold_idle_timeout_ms: int,
        status_comm: Optional[StatusCommunication] = None,
    ) -> None:
        self._db = database
        self._agent_registry = agent_registry
        self._parser = parser
        self._aggregator = aggregator
        self._hold_extractor = hold_extractor
        self._debug = debug
        self._status_comm = status_comm

        self._aggregate_round_to_us = aggregate_round_to_us
        self._aggregate_min_match_ratio = aggregate_min_match_ratio
        self._hold_idle_timeout_ms = hold_idle_timeout_ms

        self._lock = threading.Lock()
        self._session: Optional[LearningSession] = None

    @property
    def is_learning(self) -> bool:
        with self._lock:
            return self._session is not None

    @property
    def remote_id(self) -> Optional[int]:
        with self._lock:
            return self._session.remote_id if self._session else None

    @property
    def remote_name(self) -> Optional[str]:
        with self._lock:
            return self._session.remote_name if self._session else None

    @property
    def agent_id(self) -> Optional[str]:
        with self._lock:
            return self._session.agent_id if self._session else None

    def is_learning_for_agent(self, agent_id: str) -> bool:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return False
        with self._lock:
            session = self._session
            if not session:
                return False
            return str(session.agent_id).strip() == normalized_agent_id

    def start(self, remote_id: int, extend: bool) -> Dict[str, Any]:
        with self._lock:
            if self._session is not None:
                raise RuntimeError("Learning session is already running")

        remote = self._db.remotes.get(remote_id)
        agent = self._agent_registry.resolve_agent_for_remote(remote_id, remote)

        if not extend:
            self._db.remotes.clear_buttons(remote_id)

        next_index = 1
        if extend:
            next_index = self._compute_next_button_index(remote_id)

        session = LearningSession(
            remote_id=remote_id,
            remote_name=str(remote["name"]),
            agent_id=agent.agent_id,
            extend=bool(extend),
            started_at=time.time(),
            next_button_index=next_index,
        )
        self._log(session, "info", "Learning session started", {"remote_id": remote_id, "extend": bool(extend)})

        with self._lock:
            self._session = session

        try:
            agent.learn_start({"remote_id": remote_id, "remote_name": str(remote["name"])})
            self._agent_registry.mark_agent_activity(agent.agent_id)
        except Exception:
            with self._lock:
                self._session = None
            raise

        # Broadcast initial status so connected clients can render immediately.
        self._publish_status(self._session_to_dict(session, active=True))

        return self.status()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            session = self._session
            self._session = None

        if session:
            try:
                agent = self._agent_registry.get_agent_by_id(session.agent_id)
                agent.learn_stop({"remote_id": session.remote_id, "remote_name": session.remote_name})
                self._agent_registry.mark_agent_activity(session.agent_id)
            except Exception:
                pass
            self._log(session, "info", "Learning session stopped")
            self._publish_status({"learn_enabled": False})
            return self._session_to_dict(session, active=False)

        return {"learn_enabled": False}

    def capture(
        self,
        remote_id: int,
        mode: str,
        takes: int,
        timeout_ms: int,
        overwrite: bool,
        button_name: Optional[str],
    ) -> Dict[str, Any]:
        mode = mode.strip().lower()
        if mode not in ("press", "hold"):
            raise ValueError("mode must be 'press' or 'hold'")
        if takes <= 0:
            raise ValueError("takes must be > 0")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be > 0")

        session = self._get_session_or_raise(remote_id)

        if mode == "press":
            return self._capture_press(session, takes=takes, timeout_ms=timeout_ms, overwrite=overwrite, button_name=button_name)

        return self._capture_hold(session, timeout_ms=timeout_ms, overwrite=overwrite, button_name=button_name)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            session = self._session

        if not session:
            return {"learn_enabled": False}

        return self._session_to_dict(session, active=True)

    def apply_learning_settings(self, settings: Dict[str, Any]) -> None:
        # Keep capture tuning aligned with stored settings.
        if not settings:
            return
        with self._lock:
            if "aggregate_round_to_us" in settings:
                self._aggregate_round_to_us = int(settings["aggregate_round_to_us"])
            if "aggregate_min_match_ratio" in settings:
                self._aggregate_min_match_ratio = float(settings["aggregate_min_match_ratio"])
            if "hold_idle_timeout_ms" in settings:
                self._hold_idle_timeout_ms = int(settings["hold_idle_timeout_ms"])

    # -----------------------------
    # Internal
    # -----------------------------

    def _get_session_or_raise(self, remote_id: int) -> LearningSession:
        with self._lock:
            session = self._session

        if not session:
            raise RuntimeError("Learning session is not running")
        if int(session.remote_id) != int(remote_id):
            raise RuntimeError("Learning session is running for a different remote")
        return session

    def _get_agent_or_raise(self, session: LearningSession):
        return self._agent_registry.get_agent_by_id(session.agent_id)

    def _capture_press(
        self,
        session: LearningSession,
        takes: int,
        timeout_ms: int,
        overwrite: bool,
        button_name: Optional[str],
    ) -> Dict[str, Any]:
        agent = self._get_agent_or_raise(session)
        name = self._resolve_press_button_name(session, button_name)
        auto_generated = not (button_name and button_name.strip())

        existing_button = self._db.buttons.get_by_name(session.remote_id, name)
        existing_signals = self._db.signals.list_by_button(int(existing_button["id"])) if existing_button else None
        if existing_signals and not overwrite:
            raise RuntimeError("Press signal already exists (set overwrite=true to replace)")

        raw_lines: List[str] = []
        frames: List[List[int]] = []
        self._log(session, "info", "Capture press started", {"button_name": name, "takes": takes})

        for i in range(takes):
            self._log(session, "info", "Waiting for IR press", {"take": i + 1, "timeout_ms": timeout_ms})
            capture = agent.learn_capture({"timeout_ms": timeout_ms, "mode": "press"})
            self._agent_registry.mark_agent_activity(session.agent_id)
            raw = str(capture.get("raw") or "")
            stdout = str(capture.get("stdout") or "")
            stderr = str(capture.get("stderr") or "")
            if stdout or stderr:
                self._log(session, "debug", "ir-ctl output", {"stdout": stdout, "stderr": stderr})

            pulses, tail_gap_us = self._parser.parse_and_normalize(raw)

            raw_lines.append(raw)
            frames.append(pulses)

            self._log(
                session,
                "info",
                "Captured press take",
                {"take": i + 1, "pulses": len(pulses), "tail_gap_us": tail_gap_us},
            )

        aggregated, used_indices, score = self._aggregator.aggregate(
            frames,
            round_to_us=self._aggregate_round_to_us,
            min_match_ratio=self._aggregate_min_match_ratio,
        )

        press_initial = self._parser.encode_pulses(aggregated)

        # Persist only after capture succeeded.
        button = existing_button
        if not button:
            button = self._db.buttons.create(remote_id=session.remote_id, name=name)
            if auto_generated:
                session.next_button_index += 1

        button_id = int(button["id"])

        if self._debug:
            for take_idx, raw in enumerate(raw_lines):
                self._db.captures.create(button_id=button_id, mode="press", take_index=take_idx, raw_text=raw)

        signals = self._db.signals.upsert_press(
            button_id=button_id,
            press_initial=press_initial,
            press_repeat=None,
            sample_count_press=len(used_indices),
            quality_score_press=score,
            encoding="signed_us_v1",
        )

        session.last_button_id = button_id
        session.last_button_name = str(button["name"])

        self._log(session, "info", "Capture press finished", {"button_id": button_id, "quality": score})

        return {
            "remote_id": session.remote_id,
            "button": button,
            "signals": signals,
        }

    def _capture_hold(
        self,
        session: LearningSession,
        timeout_ms: int,
        overwrite: bool,
        button_name: Optional[str],
    ) -> Dict[str, Any]:
        agent = self._get_agent_or_raise(session)
        button = self._resolve_hold_button(session, button_name)
        button_id = int(button["id"])

        signals = self._db.signals.list_by_button(button_id)
        if not signals:
            raise ValueError("Press must be captured before hold can be captured")

        has_hold = bool(str(signals.get("hold_initial") or "").strip())
        if has_hold and not overwrite:
            raise RuntimeError("Hold signal already exists (set overwrite=true to replace)")

        self._log(session, "info", "Capture hold started", {"button_id": button_id, "timeout_ms": timeout_ms})

        frames_raw: List[str] = []
        frames: List[List[int]] = []
        tail_gaps: List[Optional[int]] = []
        frame_end_times: List[float] = []

        deadline = time.time() + (timeout_ms / 1000.0)

        # First message (initial)
        self._log(session, "info", "Waiting for IR hold (initial frame)", {"timeout_ms": timeout_ms})
        first_capture = agent.learn_capture({"timeout_ms": timeout_ms, "mode": "hold"})
        self._agent_registry.mark_agent_activity(session.agent_id)
        first_raw = str(first_capture.get("raw") or "")
        stdout = str(first_capture.get("stdout") or "")
        stderr = str(first_capture.get("stderr") or "")
        first_end_time = time.perf_counter()
        if stdout or stderr:
            self._log(session, "debug", "ir-ctl output", {"stdout": stdout, "stderr": stderr})
        first_pulses, first_tail_gap = self._parser.parse_and_normalize(first_raw)
        frames_raw.append(first_raw)
        frames.append(first_pulses)
        tail_gaps.append(first_tail_gap)
        frame_end_times.append(first_end_time)

        # Subsequent messages (repeats) until idle.
        while True:
            remaining_ms = int(max(0.0, (deadline - time.time()) * 1000.0))
            if remaining_ms <= 0:
                break

            per_call_timeout_ms = min(self._hold_idle_timeout_ms, remaining_ms)

            try:
                capture = agent.learn_capture({"timeout_ms": per_call_timeout_ms, "mode": "hold"})
                self._agent_registry.mark_agent_activity(session.agent_id)
                raw = str(capture.get("raw") or "")
            except TimeoutError:
                break

            received_end_time = time.perf_counter()
            pulses, tail_gap_us = self._parser.parse_and_normalize(raw)
            frames_raw.append(raw)
            frames.append(pulses)
            tail_gaps.append(tail_gap_us)
            frame_end_times.append(received_end_time)

        if len(frames) < 2:
            raise ValueError("Hold capture needs at least 2 frames. Hold the button longer or increase timeout_ms.")

        hold_initial, hold_repeat, repeat_count, repeat_score = self._hold_extractor.extract(
            frames,
            round_to_us=self._aggregate_round_to_us,
            min_match_ratio=self._aggregate_min_match_ratio,
        )

        if hold_repeat is None:
            raise ValueError("Failed to extract a repeat frame from the hold capture")

        hold_initial_text = self._parser.encode_pulses(hold_initial)
        hold_repeat_text = self._parser.encode_pulses(hold_repeat)
        hold_gap_us = self._estimate_hold_gap_us(self._resolve_hold_gap_candidates(tail_gaps, frames, frame_end_times))
        if hold_gap_us is None:
            raise ValueError("Failed to infer hold gap from capture. Hold longer and try again.")

        if self._debug:
            for idx, raw in enumerate(frames_raw):
                self._db.captures.create(button_id=button_id, mode="hold", take_index=idx, raw_text=raw)

        updated = self._db.signals.update_hold(
            button_id=button_id,
            hold_initial=hold_initial_text,
            hold_repeat=hold_repeat_text,
            hold_gap_us=hold_gap_us,
            sample_count_hold=len(frames),
            quality_score_hold=repeat_score,
        )

        session.last_button_id = button_id
        session.last_button_name = str(button["name"])

        self._log(
            session,
            "info",
            "Capture hold finished",
            {"button_id": button_id, "repeat_frames": repeat_count, "quality": repeat_score, "hold_gap_us": hold_gap_us},
        )

        return {
            "remote_id": session.remote_id,
            "button": button,
            "signals": updated,
        }

    def _resolve_press_button_name(self, session: LearningSession, button_name: Optional[str]) -> str:
        if button_name and button_name.strip():
            return button_name.strip()
        return f"BTN_{session.next_button_index:04d}"

    def _resolve_hold_button(self, session: LearningSession, button_name: Optional[str]) -> Dict[str, Any]:
        if button_name and button_name.strip():
            button = self._db.buttons.get_by_name(session.remote_id, button_name.strip())
            if not button:
                raise ValueError("Unknown button name")
            return button

        if session.last_button_id is None:
            raise ValueError("button_name is required (no previous button in session)")

        button = self._db.buttons.get(session.last_button_id)
        if int(button["remote_id"]) != int(session.remote_id):
            raise RuntimeError("Last button belongs to a different remote")
        return button

    def _compute_next_button_index(self, remote_id: int) -> int:
        buttons = self._db.buttons.list(remote_id)
        best = 0
        for b in buttons:
            name = str(b.get("name") or "")
            m = re.match(r"^BTN_(\d{4})$", name)
            if not m:
                continue
            try:
                best = max(best, int(m.group(1)))
            except Exception:
                pass
        return best + 1 if best > 0 else 1

    def _log(self, session: LearningSession, level: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        session.logs.append(LogEntry(timestamp=time.time(), level=level, message=message, data=data))
        # Only broadcast when this is the active session to avoid stale updates.
        if self._session is session:
            self._publish_status(self._session_to_dict(session, active=True))

    def _publish_status(self, payload: Dict[str, Any]) -> None:
        if self._status_comm:
            self._status_comm.broadcast(payload)

    def _session_to_dict(self, session: LearningSession, active: bool) -> Dict[str, Any]:
        return {
            "learn_enabled": bool(active),
            "remote_id": session.remote_id,
            "remote_name": session.remote_name,
            "agent_id": session.agent_id,
            "extend": bool(session.extend),
            "started_at": session.started_at,
            "last_button_id": session.last_button_id,
            "last_button_name": session.last_button_name,
            "next_button_index": session.next_button_index,
            "logs": [
                {
                    "timestamp": e.timestamp,
                    "level": e.level,
                    "message": e.message,
                    "data": e.data,
                }
                for e in session.logs
            ],
        }

    def _median_int(self, values: List[int]) -> int:
        if not values:
            return 0
        values_sorted = sorted(int(v) for v in values)
        n = len(values_sorted)
        mid = n // 2
        if n % 2 == 1:
            return int(values_sorted[mid])
        return int((values_sorted[mid - 1] + values_sorted[mid]) / 2)

    def _estimate_hold_gap_us(self, repeat_gaps: List[int]) -> Optional[int]:
        if not repeat_gaps:
            return None
        if len(repeat_gaps) == 1:
            return int(repeat_gaps[0])
        if len(repeat_gaps) == 2:
            return int(min(repeat_gaps))

        # Drop the largest gap to avoid the release gap skewing the repeat cadence.
        trimmed = sorted(int(v) for v in repeat_gaps)[:-1]
        return self._median_int(trimmed)

    def _resolve_hold_gap_candidates(
        self,
        tail_gaps: List[Optional[int]],
        frames: List[List[int]],
        frame_end_times: List[float],
    ) -> List[int]:
        # Prefer explicit tail gaps from the capture. If missing, fall back to timing between frames.
        tail_candidates = [gap for gap in tail_gaps[1:] if gap and gap > 0]
        if not tail_candidates and tail_gaps and tail_gaps[0] and tail_gaps[0] > 0:
            tail_candidates = [int(tail_gaps[0])]
        if tail_candidates:
            return [int(v) for v in tail_candidates]

        if len(frames) < 2 or len(frame_end_times) < 2:
            return []

        frame_durations = [sum(abs(int(v)) for v in frame) for frame in frames]
        timestamp_candidates: List[int] = []
        for idx in range(1, len(frames)):
            delta_us = int(round((frame_end_times[idx] - frame_end_times[idx - 1]) * 1_000_000))
            gap_us = delta_us - int(frame_durations[idx])
            if gap_us > 0:
                timestamp_candidates.append(gap_us)
        return timestamp_candidates
