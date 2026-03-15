import threading
import time
from typing import Dict, Any, List, Optional

from database import Database

from .agent import Agent
from .errors import AgentError


class AgentRegistry:
    def __init__(self, database: Database) -> None:
        self._db = database
        self._agents: Dict[str, Agent] = {}
        self._online_ids: set[str] = set()
        self._lock = threading.Lock()

    def register_agent(self, agent: Agent, online: Optional[bool] = None, last_seen: Optional[float] = None) -> None:
        with self._lock:
            self._agents[agent.agent_id] = agent
        status = agent.get_status()
        capabilities = agent.capabilities or {}
        reported_online = str(status.get("status") or "online").strip().lower() == "online"
        is_online = reported_online if online is None else bool(online)
        if last_seen is None and is_online:
            last_seen = time.time()
        self._db.agents.upsert(
            agent_id=agent.agent_id,
            name=agent.name,
            icon=None,
            transport=agent.transport,
            status="online" if is_online else "offline",
            can_send=self._resolve_can_send(capabilities),
            can_learn=self._resolve_can_learn(capabilities),
            sw_version=self._resolve_sw_version(capabilities),
            agent_topic=self._resolve_agent_topic(capabilities),
            last_seen=last_seen,
            pending=False,
            pairing_session_id=None,
        )
        with self._lock:
            if is_online:
                self._online_ids.add(agent.agent_id)
            else:
                self._online_ids.discard(agent.agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)
            self._online_ids.discard(agent_id)
        self._db.agents.set_status(agent_id=agent_id, status="offline", last_seen=time.time())

    def list_agents(self) -> List[Dict[str, Any]]:
        agents = self._db.agents.list()
        active_ids = self._get_active_ids()
        for agent in agents:
            agent["is_active"] = agent.get("agent_id") in active_ids
        return agents

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return None
        agent = self._db.agents.get(normalized_agent_id)
        if not agent:
            return None
        agent["is_active"] = normalized_agent_id in self._get_active_ids()
        return agent

    def update_agent(self, agent_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id must not be empty")
        if not changes:
            raise ValueError("at least one field must be provided")
        updated = self._db.agents.update_agent(
            agent_id=normalized_agent_id,
            changes=changes,
        )
        updated["is_active"] = normalized_agent_id in self._get_active_ids()
        return updated

    def resolve_agent_for_remote(self, remote_id: int, remote: Optional[Dict[str, Any]] = None) -> Agent:
        remote = remote or self._db.remotes.get(remote_id)
        raw_assigned = remote.get("assigned_agent_id")
        assigned_agent_id = str(raw_assigned).strip() if raw_assigned is not None else ""
        assigned_agent_id = assigned_agent_id or None
        if assigned_agent_id:
            return self.get_agent_by_id(assigned_agent_id)

        active_ids = self._get_active_ids()
        if not active_ids:
            raise AgentError(code="no_agents", message="No agents are available", status_code=503)
        if len(active_ids) == 1:
            selected_id = next(iter(active_ids))
            self._db.remotes.set_assigned_agent(remote_id=remote_id, assigned_agent_id=selected_id)
            return self.get_agent_by_id(selected_id)

        raise AgentError(code="agent_required", message="Remote must be assigned to an agent", status_code=400)

    def get_agent_by_id(self, agent_id: str) -> Agent:
        if not agent_id:
            raise AgentError(code="agent_required", message="Remote must be assigned to an agent", status_code=400)
        with self._lock:
            agent = self._agents.get(agent_id)
            is_online = agent_id in self._online_ids
        if not agent or not is_online:
            raise AgentError(code="agent_offline", message="Assigned agent is offline or unavailable", status_code=503)
        return agent

    def mark_agent_activity(self, agent_id: str) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        now = time.time()
        self._db.agents.set_status(agent_id=normalized_agent_id, status="online", last_seen=now)
        with self._lock:
            if normalized_agent_id in self._agents:
                self._online_ids.add(normalized_agent_id)

    def set_agent_online(self, agent_id: str, last_seen: Optional[float] = None) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        seen_at = time.time() if last_seen is None else float(last_seen)
        self._db.agents.set_status(agent_id=normalized_agent_id, status="online", last_seen=seen_at)
        with self._lock:
            if normalized_agent_id in self._agents:
                self._online_ids.add(normalized_agent_id)

    def set_agent_offline(self, agent_id: str, last_seen: Optional[float] = None) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        seen_at = time.time() if last_seen is None else float(last_seen)
        self._db.agents.set_status(agent_id=normalized_agent_id, status="offline", last_seen=seen_at)
        with self._lock:
            self._online_ids.discard(normalized_agent_id)

    def _resolve_can_send(self, capabilities: Dict[str, Any]) -> bool:
        if "can_send" in capabilities:
            return bool(capabilities.get("can_send"))
        if "canSend" in capabilities:
            return bool(capabilities.get("canSend"))
        return True

    def _resolve_can_learn(self, capabilities: Dict[str, Any]) -> bool:
        if "can_learn" in capabilities:
            return bool(capabilities.get("can_learn"))
        if "canLearn" in capabilities:
            return bool(capabilities.get("canLearn"))
        return False

    def _resolve_sw_version(self, capabilities: Dict[str, Any]) -> Optional[str]:
        if "sw_version" not in capabilities:
            return None
        value = str(capabilities.get("sw_version") or "").strip()
        if not value:
            return None
        return value

    def _resolve_agent_topic(self, capabilities: Dict[str, Any]) -> Optional[str]:
        if "agent_topic" not in capabilities:
            return None
        value = str(capabilities.get("agent_topic") or "").strip()
        if not value:
            return None
        return value

    def _get_active_ids(self) -> set[str]:
        with self._lock:
            return set(self._online_ids)
