#!/usr/bin/env python3
import json
import signal
import threading
from typing import Optional

from jmqtt import QualityOfService as QoS

from agents import LocalAgent, LocalTransport
from connections import (
    AgentRuntimeStateStore,
    AgentCommandHandler,
    AgentLogReporter,
    PairingManagerAgent,
    RuntimeLoader,
)
from electronics.ir_ctl_engine import IrCtlEngine
from electronics.ir_signal_parser import IrSignalParser
from helper import Environment
from runtime_version import SOFTWARE_VERSION

AGENT_LOG_STREAM_LEVEL = "info"
AGENT_PROTOCOL_VERSION = "1"

env = Environment()
parser = IrSignalParser()
engine = IrCtlEngine(
    ir_rx_device=env.ir_rx_device,
    ir_tx_device=env.ir_tx_device,
    wideband_default=env.ir_wideband,
)
local_transport = LocalTransport(engine=engine, parser=parser)
local_agent = LocalAgent(transport=local_transport, agent_id="local-agent-runtime", name="Local Agent Runtime")

runtime_loader = RuntimeLoader(
    settings_store=None,
    settings_cipher=None,
    role="agent",
    environment=env,
)
state_store = AgentRuntimeStateStore(
    runtime_loader=runtime_loader,
    agent_id_resolver=lambda: _resolve_runtime_agent_uid(),
    static_state={
        "agent_type": "docker",
        "protocol_version": AGENT_PROTOCOL_VERSION,
        "sw_version": SOFTWARE_VERSION,
        "can_send": True,
        "can_learn": True,
        "ota_supported": False,
        "reboot_required": False,
        "runtime_commands": [
            "runtime/debug/get",
            "runtime/debug/set",
            "runtime/config/get",
        ],
    },
)
agent_log_reporter = AgentLogReporter(
    agent_id_resolver=lambda: _resolve_runtime_agent_uid(),
    logger_name="agent_runtime_events",
    dispatch=lambda agent_id, event: _dispatch_runtime_log(agent_id, event),
    min_dispatch_level=AGENT_LOG_STREAM_LEVEL,
)
local_agent.set_log_reporter(agent_log_reporter)
pairing_manager = PairingManagerAgent(
    runtime_loader=runtime_loader,
    binding_store=state_store,
    readable_name="IR Agent",
    sw_version=SOFTWARE_VERSION,
    can_send=True,
    can_learn=True,
    agent_type="docker",
    protocol_version=AGENT_PROTOCOL_VERSION,
    ota_supported=False,
    reset_binding=env.agent_pairing_reset,
    log_reporter=agent_log_reporter,
)
command_handler = AgentCommandHandler(
    runtime_loader=runtime_loader,
    binding_store=state_store,
    local_agent=local_agent,
    log_reporter=agent_log_reporter,
)
state_store.set_debug_change_handler(
    lambda enabled: agent_log_reporter.set_min_dispatch_level("debug" if enabled else AGENT_LOG_STREAM_LEVEL)
)
_shutdown_event = threading.Event()


def _handle_shutdown_signal(signum: int, frame: Optional[object]) -> None:
    _shutdown_event.set()


def _resolve_runtime_agent_uid() -> str:
    client_id = str(runtime_loader.mqtt_client_id() or "").strip()
    if client_id:
        return client_id
    runtime_status = runtime_loader.status()
    fallback = str(runtime_status.get("client_id") or runtime_status.get("node_id") or "").strip()
    return fallback


def _dispatch_runtime_log(agent_id: str, event: dict) -> None:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return
    connection = runtime_loader.mqtt_connection()
    if connection is None:
        return
    topic = f"ir/agents/{normalized_agent_id}/logs"
    try:
        connection.publish(
            topic,
            json.dumps(event, separators=(",", ":")),
            qos=QoS.AtMostOnce,
            retain=False,
        )
    except Exception:
        # Do not fail agent runtime on non-critical log publishing errors.
        pass


def run() -> int:
    runtime_loader.start()
    state_store.start()
    agent_log_reporter.set_min_dispatch_level("debug" if state_store.debug_enabled() else AGENT_LOG_STREAM_LEVEL)
    pairing_manager.start()
    command_handler.start()
    try:
        while not _shutdown_event.wait(timeout=1.0):
            pass
        return 0
    finally:
        command_handler.stop()
        pairing_manager.stop()
        state_store.stop()
        runtime_loader.stop()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    raise SystemExit(run())
