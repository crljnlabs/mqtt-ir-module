#!/usr/bin/env python3
import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Header, APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents import (
    AgentRegistry,
    AgentError,
    LocalAgent,
    LocalTransport,
    MqttAgent,
    MqttTransport,
)
from api_models import (
    RemoteCreate,
    RemoteUpdate,
    AgentUpdate,
    AgentDebugUpdate,
    AgentRuntimeConfigUpdate,
    AgentOtaRequest,
    PairingOpenRequest,
    LearnStart,
    LearnCapture,
    ButtonUpdate,
    SendRequest,
    SettingsUpdate,
    AgentErrorResponse,
    LearnStartResponse,
    LearnCaptureResponse,
    SendResponse,
)
from electronics import IrLearningService
from electronics.ir_ctl_engine import IrCtlEngine
from electronics.ir_hold_extractor import IrHoldExtractor
from electronics.ir_signal_aggregator import IrSignalAggregator
from electronics.ir_signal_parser import IrSignalParser
from electronics.status_communication import StatusCommunication
from connections import (
    AgentAvailabilityHub,
    AgentCommandClientHub,
    AgentInstallationStateHub,
    AgentLogHub,
    AgentLogReporter,
    AgentRuntimeStateHub,
    PairingManagerHub,
    RuntimeLoader,
)
from firmware import FirmwareCatalog
from helper import Environment, SettingsCipher
from database import Database
from marketplace import GitHubMarketplaceIndex, InstallService
from marketplace.ir_protocol_utils import get_mqtt_protocol_payload
from pydantic import BaseModel
from runtime_version import SOFTWARE_VERSION

LOCAL_AGENT_LOG_STREAM_LEVEL = "info"
# Protocol version integers — increment the relevant constant for any breaking change.
# system: state topic structure, pairing, OTA handshake, LWT format → mismatch requires reflash
# send: IR send command topic/payload format
# learn: IR learn flow topics/payloads
SYSTEM_VERSION = 1
SEND_VERSION = 1
LEARN_VERSION = 1

env = Environment()
database = Database(data_dir=env.data_folder)
settings_cipher = SettingsCipher(env.settings_master_key)
firmware_catalog = FirmwareCatalog(root_dir=env.firmware_dir)
marketplace_index = GitHubMarketplaceIndex(database=database)
install_service = InstallService(database=database)

parser = IrSignalParser()
aggregator = IrSignalAggregator()
hold_extractor = IrHoldExtractor(aggregator)
engine = IrCtlEngine(
    ir_rx_device=env.ir_rx_device,
    ir_tx_device=env.ir_tx_device,
    wideband_default=env.ir_wideband,
)
status_comm = StatusCommunication()
agent_registry = AgentRegistry(database=database)
local_transport = LocalTransport(engine=engine, parser=parser)
local_agent = LocalAgent(transport=local_transport, agent_id="local-hub-agent")
runtime_loader = RuntimeLoader(
    settings_store=database.settings,
    settings_cipher=settings_cipher,
    role="hub",
    environment=env,
)
agent_log_hub = AgentLogHub(runtime_loader=runtime_loader, database=database, local_agent_id=local_agent.agent_id)
local_agent_log_reporter = AgentLogReporter(
    agent_id_resolver=lambda: local_agent.agent_id,
    logger_name="local_hub_agent_events",
    dispatch=lambda agent_id, event: agent_log_hub.record_local(agent_id, event),
    min_dispatch_level=LOCAL_AGENT_LOG_STREAM_LEVEL,
)
local_agent.set_log_reporter(local_agent_log_reporter)
pairing_manager = PairingManagerHub(
    runtime_loader=runtime_loader,
    database=database,
    sw_version=SOFTWARE_VERSION,
    auto_open=False,
)
command_client = AgentCommandClientHub(
    runtime_loader=runtime_loader,
    on_agent_timeout=lambda agent_id: _handle_mqtt_agent_timeout(agent_id),
)
runtime_state_hub = AgentRuntimeStateHub(runtime_loader=runtime_loader, database=database, pairing_manager=pairing_manager)
installation_state_hub = AgentInstallationStateHub(runtime_loader=runtime_loader)
availability_hub = AgentAvailabilityHub(
    runtime_loader=runtime_loader,
    agent_registry=agent_registry,
    agent_log_hub=agent_log_hub,
)

learning_defaults = database.settings.get_learning_defaults()
learning = IrLearningService(
    database=database,
    agent_registry=agent_registry,
    parser=parser,
    aggregator=aggregator,
    hold_extractor=hold_extractor,
    debug=env.debug,
    aggregate_round_to_us=learning_defaults["aggregate_round_to_us"],
    aggregate_min_match_ratio=learning_defaults["aggregate_min_match_ratio"],
    hold_idle_timeout_ms=learning_defaults["hold_idle_timeout_ms"],
    status_comm=status_comm,
)


def require_api_key(x_api_key: Optional[str]) -> None:
    if not env.api_key:
        return
    if not x_api_key or x_api_key != env.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def agent_error_response(error: AgentError) -> JSONResponse:
    payload = AgentErrorResponse(code=error.code, message=error.message)
    return JSONResponse(
        status_code=error.status_code,
        content=payload.model_dump(),
    )


def apply_hub_agent_setting(enabled: bool) -> None:
    if enabled:
        agent_registry.register_agent(local_agent)
    else:
        agent_registry.unregister_agent(local_agent.agent_id)
        agent_log_hub.clear_agent_logs(local_agent.agent_id)


def _handle_mqtt_agent_timeout(agent_id: str) -> None:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return
    seen_at = time.time()
    agent_registry.set_agent_offline(agent_id=normalized_agent_id)
    agent_log_hub.record_system(
        agent_id=normalized_agent_id,
        event={
            "ts": seen_at,
            "level": "warn",
            "category": "transport",
            "message": "Agent command timeout; marked offline",
            "error_code": "agent_timeout",
            "meta": {
                "source": "command_client",
            },
        },
    )


def register_external_mqtt_agent(agent_data: Dict[str, Any], online: bool = True) -> None:
    agent_id = str(agent_data.get("agent_id") or "").strip()
    if not agent_id:
        return

    runtime_state = runtime_state_hub.get_state(agent_id) or {}
    agent_name = str(agent_data.get("name") or "").strip() or agent_id
    capabilities: Dict[str, Any] = {
        "can_send": bool(agent_data.get("can_send")),
        "can_learn": bool(agent_data.get("can_learn")),
    }
    sw_version = str(agent_data.get("sw_version") or "").strip()
    if sw_version:
        capabilities["sw_version"] = sw_version
    agent_topic = str(agent_data.get("agent_topic") or "").strip()
    if agent_topic:
        capabilities["agent_topic"] = agent_topic
    agent_type = str(runtime_state.get("agent_type") or "").strip().lower()
    if agent_type:
        capabilities["agent_type"] = agent_type
    capabilities["ota_supported"] = bool(runtime_state.get("ota_supported"))
    if runtime_state.get("can_learn_hold_batch"):
        capabilities["can_learn_hold_batch"] = True

    transport = MqttTransport(command_client=command_client, agent_id=agent_id)
    agent = MqttAgent(
        transport=transport,
        agent_id=agent_id,
        name=agent_name,
        capabilities=capabilities,
    )
    last_seen_raw = agent_data.get("last_seen")
    last_seen = None
    if last_seen_raw is not None:
        try:
            last_seen = float(last_seen_raw)
        except Exception:
            last_seen = None
    agent_registry.register_agent(agent, online=online, last_seen=last_seen)


def register_external_mqtt_agents_from_db() -> None:
    for agent_data in database.agents.list():
        transport = str(agent_data.get("transport") or "").strip()
        pending = bool(agent_data.get("pending"))
        if transport != "mqtt" or pending:
            continue
        register_external_mqtt_agent(agent_data, online=False)


def resolve_hub_agent_setting() -> bool:
    settings = database.settings.get_ui_settings()
    hub_is_agent = bool(settings.get("hub_is_agent", True))
    if env.local_agent_enabled is None:
        return hub_is_agent
    if env.local_agent_enabled != hub_is_agent:
        database.settings.update_ui_settings(hub_is_agent=env.local_agent_enabled)
    return bool(env.local_agent_enabled)


def decorate_settings_payload(settings: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(settings or {})
    payload["settings_master_key_configured"] = settings_cipher.is_configured
    payload["mqtt_status"] = runtime_loader.status()
    return payload


def _normalize_agent_type(value: Any, transport: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized:
        return normalized
    if transport == "local":
        return "local"
    return ""


def _decorate_agent_payload(agent: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(agent or {})
    agent_id = str(payload.get("agent_id") or "").strip()
    transport = str(payload.get("transport") or "").strip().lower()
    runtime_state = runtime_state_hub.get_state(agent_id) or {}

    can_send = bool(payload.get("can_send"))
    can_learn = bool(payload.get("can_learn"))
    if "can_send" in runtime_state:
        can_send = bool(runtime_state.get("can_send"))
    if "can_learn" in runtime_state:
        can_learn = bool(runtime_state.get("can_learn"))

    sw_version = str(runtime_state.get("sw_version") or payload.get("sw_version") or "").strip()
    agent_type = _normalize_agent_type(runtime_state.get("agent_type"), transport=transport)
    ota_supported = bool(runtime_state.get("ota_supported"))
    reboot_required = bool(runtime_state.get("reboot_required"))

    # Version compatibility — compare agent's reported versions against hub constants.
    # Missing version (0) is treated as compatible to avoid false blocks during startup.
    agent_system = int(runtime_state.get("system_version") or 0)
    agent_send = int(runtime_state.get("send_version") or 0)
    agent_learn = int(runtime_state.get("learn_version") or 0)
    compatible_system = agent_system == 0 or agent_system == SYSTEM_VERSION
    compatible_send = agent_send == 0 or agent_send == SEND_VERSION
    compatible_learn = agent_learn == 0 or agent_learn == LEARN_VERSION

    runtime_payload: Dict[str, Any] = {
        "agent_type": agent_type,
        "sw_version": sw_version,
        "can_send": can_send,
        "can_learn": can_learn,
        "ota_supported": ota_supported,
        "reboot_required": reboot_required,
        "last_reset_reason": str(runtime_state.get("last_reset_reason") or "").strip().lower(),
        "last_reset_code": runtime_state.get("last_reset_code"),
        "last_reset_crash": bool(runtime_state.get("last_reset_crash")),
        "free_heap": runtime_state.get("free_heap"),
        "ir_rx_pin": runtime_state.get("ir_rx_pin"),
        "ir_tx_pin": runtime_state.get("ir_tx_pin"),
        "state_seen_at": runtime_state.get("state_seen_at"),
    }

    ota_payload = {
        "supported": bool(ota_supported),
        "agent_type": agent_type,
        "current_version": sw_version,
        "latest_version": "",
        "update_available": False,
    }
    if agent_type:
        ota_payload = firmware_catalog.ota_status(
            agent_type=agent_type,
            current_version=sw_version,
            ota_supported=ota_supported,
        )
    ota_payload["reboot_required"] = reboot_required

    if sw_version:
        installation_state_hub.reconcile_with_runtime_version(agent_id=agent_id, current_version=sw_version)
    installation = installation_state_hub.get_state(agent_id) or {}
    if installation:
        installation.setdefault("current_version", sw_version)
    else:
        installation = {
            "status": "idle",
            "in_progress": False,
            "progress_pct": None,
            "target_version": "",
            "current_version": sw_version,
            "message": "",
            "error_code": "",
            "updated_at": None,
        }

    payload["can_send"] = can_send
    payload["can_learn"] = can_learn
    payload["sw_version"] = sw_version
    payload["agent_type"] = agent_type
    payload["runtime"] = runtime_payload
    payload["ota"] = ota_payload
    payload["capabilities"] = {
        "can_send": can_send,
        "can_learn": can_learn,
        "sw_version": sw_version,
        "agent_type": agent_type,
        "ota_supported": ota_supported,
    }
    payload["compatibility"] = {
        "system": compatible_system,
        "send": compatible_send,
        "learn": compatible_learn,
    }
    payload["installation"] = installation
    return payload


def _require_agent_not_installing(agent_id: str) -> None:
    installation = installation_state_hub.get_state(agent_id) or {}
    if not bool(installation.get("in_progress")):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "ota_in_progress",
            "message": "OTA installation is in progress for this agent",
            "status": str(installation.get("status") or ""),
            "progress_pct": installation.get("progress_pct"),
            "target_version": str(installation.get("target_version") or ""),
        },
    )


def _require_agent_compatible_send(agent_id: str) -> None:
    """Raise AgentError if the agent's send protocol version mismatches the hub."""
    from agents.errors import AgentError
    state = runtime_state_hub.get_state(agent_id) or {}
    agent_send = int(state.get("send_version") or 0)
    if agent_send != 0 and agent_send != SEND_VERSION:
        raise AgentError(
            code="agent_incompatible_send",
            message="Agent send protocol is incompatible. Firmware update required.",
            status_code=503,
        )


def _require_agent_compatible_learn(agent_id: str) -> None:
    """Raise AgentError if the agent's learn protocol version mismatches the hub."""
    from agents.errors import AgentError
    state = runtime_state_hub.get_state(agent_id) or {}
    agent_learn = int(state.get("learn_version") or 0)
    if agent_learn != 0 and agent_learn != LEARN_VERSION:
        raise AgentError(
            code="agent_incompatible_learn",
            message="Agent learn protocol is incompatible. Firmware update required.",
            status_code=503,
        )


_APP_LOG_MODULES = (
    "agents", "connections", "database", "electronics",
    "firmware", "helper", "marketplace",
)


def _setup_app_logging() -> None:
    """Align all app module loggers with uvicorn's output style.

    Uvicorn owns the root logger; we attach a dedicated handler to each app
    sub-package so their messages appear with level + name instead of a bare
    message string.
    """
    fmt = logging.Formatter("%(levelname)-9s %(name)s - %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    for name in _APP_LOG_MODULES:
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        log.addHandler(handler)
        log.propagate = False  # don't double-log through uvicorn's root handler


_prune_logger = logging.getLogger("connections.log_retention")
_LOG_PRUNE_INTERVAL_SECONDS = 3600


def _prune_logs_once() -> None:
    try:
        retention_days = database.settings.get_log_settings().get("log_retention_days", 7)
        removed = database.logs.prune(retention_days)
        if removed:
            _prune_logger.info(f"Pruned {removed} log entries older than {retention_days} days")
    except Exception as exc:
        _prune_logger.warning(f"Log retention prune failed: {exc}")


def _prune_logs_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(_LOG_PRUNE_INTERVAL_SECONDS):
        _prune_logs_once()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_app_logging()
    database.init()
    firmware_catalog.ensure_layout()
    # Start marketplace background sync if local index is empty
    marketplace_index.auto_sync()
    # Load persisted learning defaults after the settings table exists.
    learning.apply_learning_settings(database.settings.get_learning_settings())
    # Store the running loop so sync code can broadcast status updates.
    loop = asyncio.get_running_loop()
    status_comm.attach_loop(loop)
    agent_log_hub.attach_loop(loop)

    apply_hub_agent_setting(resolve_hub_agent_setting())
    runtime_loader.start()
    agent_log_hub.start()
    runtime_state_hub.start()
    installation_state_hub.start()
    command_client.start()
    register_external_mqtt_agents_from_db()
    availability_hub.start()
    pairing_manager.start()

    # Debug capture data can grow quickly; keep it only when DEBUG=true.
    if not env.debug:
        database.captures.clear()

    # Prune logs that exceed the retention window, then keep pruning hourly.
    _prune_logs_once()
    _log_prune_stop_event = threading.Event()
    _log_prune_thread = threading.Thread(
        target=_prune_logs_loop,
        args=(_log_prune_stop_event,),
        daemon=True,
        name="log-retention",
    )
    _log_prune_thread.start()

    try:
        yield
    finally:
        _log_prune_stop_event.set()
        pairing_manager.stop()
        availability_hub.stop()
        command_client.stop()
        installation_state_hub.stop()
        runtime_state_hub.stop()
        agent_log_hub.stop()
        runtime_loader.stop()
        learning.stop()


app = FastAPI(
    title="mqtt-ir-module",
    version=SOFTWARE_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.exception_handler(AgentError)
async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
    return agent_error_response(exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@api.get("/version")
def version() -> Dict[str, Any]:
    return {"version": SOFTWARE_VERSION}


@api.get("/status/electronics")
def status_electronics() -> Dict[str, Any]:
    return {
        "ir_device": env.ir_rx_device,
        "ir_rx_device": env.ir_rx_device,
        "ir_tx_device": env.ir_tx_device,
        "debug": env.debug,
    }


@api.get("/status/learning")
def status_learning() -> Dict[str, Any]:
    return {
        "learn_enabled": learning.is_learning,
        "learn_remote_id": learning.remote_id,
        "learn_remote_name": learning.remote_name,
        "learn_agent_id": learning.agent_id,
    }


@api.get("/status/mqtt")
def status_mqtt() -> Dict[str, Any]:
    return runtime_loader.status()


@api.get("/status/pairing")
def status_pairing() -> Dict[str, Any]:
    return pairing_manager.status()


@api.get("/agents")
def list_agents() -> List[Dict[str, Any]]:
    return [_decorate_agent_payload(agent) for agent in agent_registry.list_agents()]


@api.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> Dict[str, Any]:
    agent = agent_registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent_id")
    return _decorate_agent_payload(agent)


def _require_registered_agent(agent_id: str) -> Dict[str, Any]:
    agent = agent_registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent_id")
    return agent


def _require_mqtt_agent(agent_id: str) -> Dict[str, Any]:
    agent = _require_registered_agent(agent_id)
    transport = str(agent.get("transport") or "").strip().lower()
    if transport != "mqtt":
        raise HTTPException(status_code=400, detail="Only MQTT agents are supported for this operation")
    return agent


@api.get("/agents/{agent_id}/debug")
def get_agent_debug(agent_id: str) -> Dict[str, Any]:
    agent = _require_mqtt_agent(agent_id)
    result = command_client.runtime_debug_get(agent_id=agent_id)
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "debug": bool(result.get("debug")),
    }


@api.put("/agents/{agent_id}/debug")
def update_agent_debug(
    agent_id: str,
    body: AgentDebugUpdate,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    agent = _require_mqtt_agent(agent_id)
    _require_agent_not_installing(str(agent.get("agent_id") or agent_id))
    result = command_client.runtime_debug_set(agent_id=agent_id, debug=body.debug)
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "debug": bool(result.get("debug")),
    }


@api.get("/agents/{agent_id}/runtime-config")
def get_agent_runtime_config(agent_id: str) -> Dict[str, Any]:
    agent = _require_mqtt_agent(agent_id)
    result = command_client.runtime_config_get(agent_id=agent_id)
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "ir_rx_pin": result.get("ir_rx_pin"),
        "ir_tx_pin": result.get("ir_tx_pin"),
        "reboot_required": bool(result.get("reboot_required")),
    }


@api.put("/agents/{agent_id}/runtime-config")
def update_agent_runtime_config(
    agent_id: str,
    body: AgentRuntimeConfigUpdate,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    agent = _require_mqtt_agent(agent_id)
    _require_agent_not_installing(str(agent.get("agent_id") or agent_id))
    decorated = _decorate_agent_payload(agent)
    runtime = decorated.get("runtime") if isinstance(decorated.get("runtime"), dict) else {}
    if str(runtime.get("agent_type") or "").strip().lower() != "esp32":
        raise HTTPException(status_code=400, detail="Runtime config is supported only for esp32 agents")

    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="at least one setting must be provided")
    result = command_client.runtime_config_set(agent_id=agent_id, payload=payload)
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "ir_rx_pin": result.get("ir_rx_pin"),
        "ir_tx_pin": result.get("ir_tx_pin"),
        "reboot_required": bool(result.get("reboot_required")),
    }


@api.post("/agents/{agent_id}/reboot")
def reboot_agent(agent_id: str, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    agent = _require_mqtt_agent(agent_id)
    _require_agent_not_installing(str(agent.get("agent_id") or agent_id))
    result = command_client.runtime_reboot(agent_id=agent_id)
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "result": result,
    }


@api.get("/firmware")
def list_firmware(agent_type: str = FirmwareCatalog.DEFAULT_AGENT_TYPE) -> Dict[str, Any]:
    items = firmware_catalog.list_firmwares(agent_type=agent_type, include_non_installable=True)
    latest = firmware_catalog.latest_firmware(agent_type=agent_type, include_non_installable=False)
    return {
        "agent_type": str(agent_type or "").strip().lower() or FirmwareCatalog.DEFAULT_AGENT_TYPE,
        "items": items,
        "latest_installable_version": str(latest.get("version") or "") if latest else "",
    }


@api.get("/firmware/webtools-manifest")
def get_webtools_manifest(request: Request, agent_type: str = FirmwareCatalog.DEFAULT_AGENT_TYPE) -> Dict[str, Any]:
    try:
        return firmware_catalog.build_webtools_manifest(
            request=request,
            public_base_url=env.public_base_url,
            agent_type=agent_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@api.post("/agents/{agent_id}/ota")
def ota_update_agent(
    request: Request,
    agent_id: str,
    body: AgentOtaRequest,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    agent = _require_mqtt_agent(agent_id)
    normalized_agent_id = str(agent.get("agent_id") or agent_id)
    _require_agent_not_installing(normalized_agent_id)
    decorated = _decorate_agent_payload(agent)
    runtime = decorated.get("runtime") if isinstance(decorated.get("runtime"), dict) else {}
    if str(runtime.get("agent_type") or "").strip().lower() != "esp32":
        raise HTTPException(status_code=400, detail="OTA is supported only for esp32 agents")
    if not bool(runtime.get("ota_supported")):
        raise HTTPException(status_code=400, detail="Agent does not report OTA support")

    try:
        firmware = firmware_catalog.resolve_firmware(
            agent_type="esp32",
            version=body.version,
            require_installable=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Reboot the agent before OTA to ensure a clean WiFi stack and fresh RAM.
    last_seen_before = float(agent.get("last_seen") or 0)
    command_client.runtime_reboot(agent_id=normalized_agent_id)

    reboot_timeout = 45
    reboot_deadline = time.time() + reboot_timeout
    came_back_online = False
    while time.time() < reboot_deadline:
        time.sleep(1)
        current = agent_registry.get_agent(normalized_agent_id)
        if (
            current
            and str(current.get("status") or "").strip().lower() == "online"
            and float(current.get("last_seen") or 0) > last_seen_before
        ):
            came_back_online = True
            break
    if not came_back_online:
        raise HTTPException(status_code=503, detail="Agent did not come back online after reboot")

    ota_file = str(firmware.get("ota_file") or "").strip()
    ota_url = firmware_catalog.build_firmware_url(
        request=request,
        public_base_url=env.public_base_url,
        filename=ota_file,
    )
    payload = {
        "version": str(firmware.get("version") or ""),
        "url": ota_url,
        "sha256": str(firmware.get("ota_sha256") or ""),
    }
    result = command_client.runtime_ota_start(agent_id=normalized_agent_id, payload=payload)
    agent_registry.mark_agent_activity(normalized_agent_id)
    return {
        "agent_id": normalized_agent_id,
        "requested_version": payload["version"],
        "url": ota_url,
        "result": result,
    }


@api.post("/agents/{agent_id}/ota/cancel")
def ota_cancel_agent(
    agent_id: str,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    agent = _require_mqtt_agent(agent_id)
    decorated = _decorate_agent_payload(agent)
    runtime = decorated.get("runtime") if isinstance(decorated.get("runtime"), dict) else {}
    if str(runtime.get("agent_type") or "").strip().lower() != "esp32":
        raise HTTPException(status_code=400, detail="OTA is supported only for esp32 agents")
    if not bool(runtime.get("ota_supported")):
        raise HTTPException(status_code=400, detail="Agent does not report OTA support")
    result = command_client.runtime_ota_cancel(agent_id=agent_id)
    agent_registry.mark_agent_activity(agent_id)
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "result": result,
    }


@api.post("/agents/{agent_id}/installation/reset")
def reset_agent_installation_state(
    agent_id: str,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    agent = _require_mqtt_agent(agent_id)
    reset = installation_state_hub.reset_state(str(agent.get("agent_id") or agent_id))
    return {
        "agent_id": str(agent.get("agent_id") or agent_id),
        "reset": bool(reset),
    }



@api.get("/logs")
def get_logs(
    level: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    category: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    levels = _split_csv_param(level)
    source_types = _split_csv_param(source_type)
    source_ids = _split_csv_param(source_id)
    categories = _split_csv_param(category)
    items = database.logs.query(
        levels=levels or None,
        source_types=source_types or None,
        source_ids=source_ids or None,
        categories=categories or None,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )
    return {"items": items, "count": len(items)}


@api.delete("/logs")
def delete_logs(
    level: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    category: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    levels = _split_csv_param(level)
    source_types = _split_csv_param(source_type)
    source_ids = _split_csv_param(source_id)
    categories = _split_csv_param(category)
    deleted = database.logs.delete(
        levels=levels or None,
        source_types=source_types or None,
        source_ids=source_ids or None,
        categories=categories or None,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return {"deleted": deleted}


@api.websocket("/logs/ws")
async def logs_ws(websocket: WebSocket) -> None:
    await agent_log_hub.connect_global(websocket)
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await agent_log_hub.disconnect_global(websocket)


def _split_csv_param(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


@api.put("/agents/{agent_id}")
def update_agent(
    agent_id: str,
    body: AgentUpdate,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    _require_agent_not_installing(agent_id)
    try:
        changes = body.model_dump(exclude_unset=True)
        updated = agent_registry.update_agent(
            agent_id=agent_id,
            changes=changes,
        )
        return _decorate_agent_payload(updated)
    except ValueError as e:
        message = str(e)
        if message == "Unknown agent_id":
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)


@api.delete("/agents/{agent_id}")
def delete_agent(
    agent_id: str,
    force: bool = False,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    if agent_id == local_agent.agent_id:
        raise HTTPException(status_code=400, detail="Local hub agent cannot be removed")
    if not bool(force):
        _require_agent_not_installing(agent_id)
    try:
        result = pairing_manager.unpair_and_delete_agent(agent_id, force=bool(force))
        agent_registry.unregister_agent(agent_id)
        agent_log_hub.clear_agent_logs(agent_id)
        runtime_state_hub.clear_state(agent_id)
        installation_state_hub.reset_state(agent_id)
        return result
    except ValueError as e:
        message = str(e)
        if message == "Unknown agent_id":
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@api.post("/pairing/open")
def pairing_open(
    body: PairingOpenRequest,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        duration = pairing_manager.DEFAULT_WINDOW_SECONDS
        return pairing_manager.open_pairing(duration_seconds=duration)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.post("/pairing/close")
def pairing_close(x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return pairing_manager.close_pairing()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.post("/pairing/accept/{agent_id}")
def pairing_accept(agent_id: str, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        accepted = pairing_manager.accept_offer(agent_id=agent_id)
        register_external_mqtt_agent(accepted, online=True)
        return accepted
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------
# Settings (UI)
# -----------------


@api.get("/settings")
def get_settings() -> Dict[str, Any]:
    return decorate_settings_payload(database.settings.get_ui_settings())


@api.put("/settings")
def update_settings(body: SettingsUpdate, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    if body.hub_is_agent is not None:
        raise HTTPException(
            status_code=400,
            detail="hub_is_agent is managed via LOCAL_AGENT_ENABLED and is read-only in settings.",
        )
    if (
        body.theme is None
        and body.language is None
        and body.homeassistant_enabled is None
        and body.mqtt_host is None
        and body.mqtt_port is None
        and body.mqtt_username is None
        and body.mqtt_password is None
        and body.mqtt_instance is None
        and body.press_takes_default is None
        and body.capture_timeout_ms_default is None
        and body.hold_idle_timeout_ms is None
        and body.aggregate_round_to_us is None
        and body.aggregate_min_match_ratio is None
        and body.log_retention_days is None
    ):
        raise HTTPException(status_code=400, detail="at least one setting must be provided")
    try:
        mqtt_runtime_changed = any(
            value is not None
            for value in (
                body.homeassistant_enabled,
                body.mqtt_host,
                body.mqtt_port,
                body.mqtt_username,
                body.mqtt_password,
                body.mqtt_instance,
            )
        )
        updated = database.settings.update_ui_settings(
            theme=body.theme,
            language=body.language,
            homeassistant_enabled=body.homeassistant_enabled,
            mqtt_host=body.mqtt_host,
            mqtt_port=body.mqtt_port,
            mqtt_username=body.mqtt_username,
            mqtt_password=body.mqtt_password,
            mqtt_instance=body.mqtt_instance,
            settings_cipher=settings_cipher,
            press_takes_default=body.press_takes_default,
            capture_timeout_ms_default=body.capture_timeout_ms_default,
            hold_idle_timeout_ms=body.hold_idle_timeout_ms,
            aggregate_round_to_us=body.aggregate_round_to_us,
            aggregate_min_match_ratio=body.aggregate_min_match_ratio,
            log_retention_days=body.log_retention_days,
        )
        learning.apply_learning_settings(updated)
        if mqtt_runtime_changed:
            command_client.stop()
            pairing_manager.stop()
            availability_hub.stop()
            installation_state_hub.stop()
            runtime_state_hub.stop()
            agent_log_hub.stop()
            runtime_loader.reload()
            agent_log_hub.start()
            runtime_state_hub.start()
            installation_state_hub.start()
            availability_hub.start()
            command_client.start()
            pairing_manager.start()
        return decorate_settings_payload(updated)
    except ValueError as e:
        message = str(e)
        if message == "settings_master_key_missing":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "settings_master_key_missing",
                    "message": "SETTINGS_MASTER_KEY is required to store MQTT password.",
                },
            )
        if message == "mqtt_password_decrypt_failed":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "mqtt_password_decrypt_failed",
                    "message": "Stored MQTT password cannot be decrypted with the current SETTINGS_MASTER_KEY.",
                },
            )
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        message = str(e)
        if "AES-GCM settings encryption" in message:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "settings_crypto_missing",
                    "message": "The cryptography package is required to encrypt MQTT passwords.",
                },
            )
        raise HTTPException(status_code=400, detail=message)


# -----------------
# Remotes CRUD
# -----------------


@api.post("/remotes")
def create_remote(body: RemoteCreate, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return database.remotes.create(name=body.name, icon=body.icon)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.get("/remotes")
def list_remotes() -> List[Dict[str, Any]]:
    return database.remotes.list()


@api.put("/remotes/{remote_id}")
def update_remote(remote_id: int, body: RemoteUpdate, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return database.remotes.update(
            remote_id=remote_id,
            name=body.name,
            icon=body.icon,
            assigned_agent_id=body.assigned_agent_id,
            carrier_hz=body.carrier_hz,
            duty_cycle=body.duty_cycle,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.delete("/remotes/{remote_id}")
def delete_remote(remote_id: int, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return database.remotes.delete(remote_id=remote_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------
# Buttons CRUD
# -----------------


@api.get("/remotes/{remote_id}/buttons")
def list_buttons(remote_id: int) -> List[Dict[str, Any]]:
    try:
        database.remotes.get(remote_id)
        return database.buttons.list(remote_id=remote_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api.put("/buttons/{button_id}")
def rename_button(button_id: int, body: ButtonUpdate, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return database.buttons.rename(button_id=button_id, name=body.name, icon=body.icon)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.delete("/buttons/{button_id}")
def delete_button(button_id: int, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return database.buttons.delete(button_id=button_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------
# Learning
# -----------------


@api.post(
    "/learn/start",
    response_model=LearnStartResponse,
    responses={400: {"model": AgentErrorResponse}, 503: {"model": AgentErrorResponse}},
)
def learn_start(body: LearnStart, x_api_key: Optional[str] = Header(default=None)) -> LearnStartResponse:
    require_api_key(x_api_key)
    try:
        remote = database.remotes.get(body.remote_id)
        if remote:
            pre_agent = agent_registry.resolve_agent_for_remote(remote_id=body.remote_id, remote=remote)
            _require_agent_compatible_learn(pre_agent.agent_id)
        result = learning.start(remote_id=body.remote_id, extend=body.extend)
        return LearnStartResponse.model_validate(result)
    except AgentError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.post(
    "/learn/capture",
    response_model=LearnCaptureResponse,
    responses={400: {"model": AgentErrorResponse}, 503: {"model": AgentErrorResponse}},
)
def learn_capture(body: LearnCapture, x_api_key: Optional[str] = Header(default=None)) -> LearnCaptureResponse:
    require_api_key(x_api_key)

    learning_settings = database.settings.get_learning_settings()
    learning.apply_learning_settings(learning_settings)
    takes = body.takes if body.takes is not None else learning_settings["press_takes_default"]
    timeout_ms = body.timeout_ms if body.timeout_ms is not None else learning_settings["capture_timeout_ms_default"]

    try:
        result = learning.capture(
            remote_id=body.remote_id,
            mode=body.mode,
            takes=takes,
            timeout_ms=timeout_ms,
            overwrite=body.overwrite,
            button_name=body.button_name,
        )
        return LearnCaptureResponse.model_validate(result)
    except AgentError:
        raise
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.post("/learn/stop")
def learn_stop(x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    return learning.stop()


@api.get("/learn/status", response_model=LearnStartResponse)
def learn_status() -> LearnStartResponse:
    return LearnStartResponse.model_validate(learning.status())


@api.websocket("/learn/status/ws")
async def learn_status_ws(websocket: WebSocket) -> None:
    # Stream status updates over a single WebSocket to avoid frequent polling.
    await status_comm.connect(websocket)
    try:
        await status_comm.send(websocket, learning.status())
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        pass
    finally:
        await status_comm.disconnect(websocket)


# -----------------
# Sending
# -----------------


@api.post(
    "/send",
    response_model=SendResponse,
    responses={400: {"model": AgentErrorResponse}, 503: {"model": AgentErrorResponse}},
)
def send_ir(body: SendRequest, x_api_key: Optional[str] = Header(default=None)) -> SendResponse:
    require_api_key(x_api_key)

    try:
        button = database.buttons.get(body.button_id)
        signals = database.signals.list_by_button(body.button_id)
        if not signals:
            raise ValueError("No signals for button")

        remote = database.remotes.get(int(button["remote_id"]))
        agent = agent_registry.resolve_agent_for_remote(remote_id=int(remote["id"]), remote=remote)
        _require_agent_compatible_send(agent.agent_id)
        if learning.is_learning_for_agent(agent.agent_id):
            raise AgentError(code="send_while_learning", message="Cannot send while learning is active", status_code=409)

        encoding = str(signals.get("encoding") or "raw").strip().lower()
        if encoding == "protocol":
            payload = {
                "mode": body.mode,
                "hold_ms": body.hold_ms,
                "encoding": "protocol",
                "protocol": signals.get("protocol"),
                "address": signals.get("address"),
                "command_hex": signals.get("command_hex"),
            }
        else:
            payload = {
                "mode": body.mode,
                "hold_ms": body.hold_ms,
                "encoding": encoding,
                "press_initial": signals.get("press_initial"),
                "hold_initial": signals.get("hold_initial"),
                "hold_repeat": signals.get("hold_repeat"),
                "hold_gap_us": signals.get("hold_gap_us"),
                "carrier_hz": remote.get("carrier_hz"),
                "duty_cycle": remote.get("duty_cycle"),
            }

        result = agent.send(payload)
        agent_registry.mark_agent_activity(agent.agent_id)
        return SendResponse.model_validate(result)
    except AgentError:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# -----------------
# Marketplace
# -----------------


class _MarketplaceInstallBody(BaseModel):
    path: str
    remote_name: str


@api.get("/marketplace/index")
def marketplace_index_list(
    q: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return database.marketplace.search(q=q, category=category, brand=brand, source=source)


@api.get("/marketplace/categories")
def marketplace_categories() -> List[str]:
    return database.marketplace.list_categories()


@api.get("/marketplace/brands")
def marketplace_brands(category: Optional[str] = None) -> List[str]:
    return database.marketplace.list_brands(category=category)


@api.get("/marketplace/count")
def marketplace_count() -> Dict[str, Any]:
    return {"total": database.marketplace.count()}


@api.get("/marketplace/sync/status")
def marketplace_sync_status() -> Dict[str, Any]:
    return marketplace_index.get_status()


@api.post("/marketplace/sync")
def marketplace_sync(x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_api_key(x_api_key)
    started = marketplace_index.trigger_sync()
    return {"started": started}


@api.get("/marketplace/installed-paths")
def marketplace_installed_paths() -> List[str]:
    return database.remotes.list_marketplace_paths()


@api.post("/marketplace/install")
def marketplace_install(
    body: _MarketplaceInstallBody,
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    require_api_key(x_api_key)
    try:
        return install_service.install(path=body.path, remote_name=body.remote_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# Register API at /api
app.include_router(api)

# Optional: also register the same API under the public base url (so direct /base/api works without a proxy)
public_base_url = env.public_base_url  # always with trailing slash
base_prefix = public_base_url.rstrip("/")
if base_prefix:
    app.include_router(api, prefix=base_prefix)

# -----------------
# Frontend (Vite build)
# -----------------

static_dir = Path(__file__).parent / "static"
assets_dir = static_dir / "assets"
index_html = static_dir / "index.html"
firmware_files_dir = firmware_catalog.files_dir


def _render_index_html() -> str:
    if not index_html.exists():
        raise HTTPException(status_code=404, detail="Frontend not built (missing static/index.html)")

    html = index_html.read_text(encoding="utf-8", errors="replace")

    api_base = f"{public_base_url.rstrip('/')}/api"
    config = {
        "publicBaseUrl": public_base_url,
        "apiBaseUrl": api_base,
        "publicApiKey": env.public_api_key or "",
        "writeRequiresApiKey": bool(env.api_key),
    }

    # Replace placeholders (frontend/index.html contains these markers before build)
    html = html.replace("__PUBLIC_BASE_URL__", public_base_url)
    html = html.replace("__APP_CONFIG_JSON__", json.dumps(config))

    return html


if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if base_prefix:
        app.mount(f"{base_prefix}/assets", StaticFiles(directory=assets_dir), name="assets_base")

app.mount("/firmware", StaticFiles(directory=firmware_files_dir, check_dir=False), name="firmware")
if base_prefix:
    app.mount(f"{base_prefix}/firmware", StaticFiles(directory=firmware_files_dir, check_dir=False), name="firmware_base")


@app.get("/")
def frontend_index():
    return HTMLResponse(_render_index_html())


@app.get("/{path:path}")
def frontend_fallback(path: str):
    file_path = static_dir / path
    if file_path.is_file():
        return FileResponse(file_path)
    return HTMLResponse(_render_index_html())
