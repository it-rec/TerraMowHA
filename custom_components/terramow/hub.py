"""Device hub for the TerraMow integration.

The hub owns everything protocol- and state-related: the MQTT client and
its worker thread, the data point caches, the map/path HTTP fetching and
the command helpers. Entities consume it through ``basic_data.lawn_mower``
(the attribute keeps its historical name so the entity-facing API is
unchanged) and register callbacks for push updates.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import random
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

import aiohttp
import paho.mqtt.client as mqtt_client
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    APP_DP_TOPIC_FILTER,
    COMMAND_ACK_DP,
    COMMAND_ACK_TIMEOUT,
    COMPATIBILITY_INFO_DP,
    CONF_SERIAL,
    DOMAIN,
    MAP_INFO_TOPIC,
    MAP_META_TOPIC,
    MODEL_NAME_TOPIC,
    MQTT_PORT,
    MQTT_RECONNECT_BASE_DELAY,
    MQTT_RECONNECT_MAX_DELAY,
    MQTT_THREAD_JOIN_TIMEOUT,
    MQTT_USERNAME,
    PATH_HISTORY_META_TOPIC,
    PATH_META_TOPIC,
    POSE_TOPIC,
    CompatibilityStatus,
)
from .issues import (
    async_sync_base_station_maintenance_issue,
    async_sync_blade_maintenance_issue,
    async_sync_compatibility_issue,
)
from .mqtt_compat import create_mqtt_client

if TYPE_CHECKING:
    from . import TerraMowBasicData

_LOGGER = logging.getLogger(__name__)

# Define the regular expression pattern
TOPIC_PATTERN = re.compile(r"^data_point/(\d+)/robot$")
APP_TOPIC_PATTERN = re.compile(r"^data_point/(\d+)/app$")

# How many *changes* to remember per undocumented data point. Bounded so the
# diagnostics export stays small; only value changes are recorded (see
# ``on_mqtt_message``), so this is a window of transitions, not raw messages.
UNKNOWN_DP_HISTORY_MAXLEN = 30


def _decompress_and_parse(raw: bytes) -> Any:
    """Decompress (if gzip) and JSON-parse a fetched map/path body.

    Runs in the executor: ha_map_v1/ha_path_v1 bodies grow with session
    length, and parsing them on the event loop stalls it for tens of
    milliseconds on small hosts.
    """
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _make_unsubscriber[CallbackT](
    callbacks: list[CallbackT], callback: CallbackT
) -> Callable[[], None]:
    """Build an unsubscribe callable removing ``callback`` from ``callbacks``.

    Idempotent: calling the returned callable more than once (or after the
    callback was removed elsewhere) is a no-op instead of a ValueError.
    """

    def _unsubscribe() -> None:
        try:
            callbacks.remove(callback)
        except ValueError:
            pass  # already removed

    return _unsubscribe


class Mission(Enum):
    MISSION_IDLE = "MISSION_IDLE"
    MISSION_RECHARGE = "MISSION_RECHARGE"
    MISSION_GLOBAL_CLEAN = "MISSION_GLOBAL_CLEAN"
    MISSION_BUILD_MAP = "MISSION_BUILD_MAP"
    MISSION_BUILD_MAP_AND_CLEAN = "MISSION_BUILD_MAP_AND_CLEAN"
    MISSION_TEMPORARY_CLEAN = "MISSION_TEMPORARY_CLEAN"
    MISSION_BACK_TO_STARTING_POINT = "MISSION_BACK_TO_STARTING_POINT"
    MISSION_REMOTE_CONTROL_CLEAN = "MISSION_REMOTE_CONTROL_CLEAN"
    MISSION_SCHEDULE_GLOBAL_CLEAN = "MISSION_SCHEDULE_GLOBAL_CLEAN"
    MISSION_SCHEDULE_BUILD_MAP_AND_CLEAN = "MISSION_SCHEDULE_BUILD_MAP_AND_CLEAN"
    MISSION_SELECT_REGION_CLEAN = "MISSION_SELECT_REGION_CLEAN"
    MISSION_CREATE_CUSTOM_PASSAGE = "MISSION_CREATE_CUSTOM_PASSAGE"
    MISSION_BACKUP_MAP = "MISSION_BACKUP_MAP"
    MISSION_RELOCATE_BASE_STATION = "MISSION_RELOCATE_BASE_STATION"
    MISSION_USER_AUTO_CALIBRATION = "MISSION_USER_AUTO_CALIBRATION"
    MISSION_RESTORE_BACKUP_MAP = "MISSION_RESTORE_BACKUP_MAP"
    MISSION_SCHEDULE_SELECT_REGION_CLEAN = "MISSION_SCHEDULE_SELECT_REGION_CLEAN"
    MISSION_DRAW_REGION_CLEAN = "MISSION_DRAW_REGION_CLEAN"
    MISSION_EDGE_TRIM_CLEAN = "MISSION_EDGE_TRIM_CLEAN"
    MISSION_UPDATE_BACKUP_MAP = "MISSION_UPDATE_BACKUP_MAP"


class SubMission(Enum):
    SUB_MISSION_IDLE = "SUB_MISSION_IDLE"
    SUB_MISSION_RELOCATION = "SUB_MISSION_RELOCATION"
    SUB_MISSION_RETURN_TO_BASE = "SUB_MISSION_RETURN_TO_BASE"
    SUB_MISSION_OUT_OF_STATION = "SUB_MISSION_OUT_OF_STATION"
    SUB_MISSION_REMOTE_CONTROL = "SUB_MISSION_REMOTE_CONTROL"
    SUB_MISSION_SAVING_MAP = "SUB_MISSION_SAVING_MAP"
    SUB_MISSION_SETTING_BLADE_HEIGHT = "SUB_MISSION_SETTING_BLADE_HEIGHT"
    SUB_MISSION_CHARGING = "SUB_MISSION_CHARGING"
    SUB_MISSION_REMOTE_CONTROL_CLEAN = "SUB_MISSION_REMOTE_CONTROL_CLEAN"
    SUB_MISSION_DEFOGGING = "SUB_MISSION_DEFOGGING"
    SUB_MISSION_WAIT_FOR_DAYLIGHT = "SUB_MISSION_WAIT_FOR_DAYLIGHT"
    SUB_MISSION_COOLING_DOWN_MOTOR = "SUB_MISSION_COOLING_DOWN_MOTOR"
    SUB_MISSION_WAIT_FOR_RAIN_TO_STOP = "SUB_MISSION_WAIT_FOR_RAIN_TO_STOP"
    SUB_MISSION_FLEXIBLE_STATION_WAIT = "SUB_MISSION_FLEXIBLE_STATION_WAIT"


class MissionState(Enum):
    MISSION_STATE_IDLE = "MISSION_STATE_IDLE"
    MISSION_STATE_RUNNING = "MISSION_STATE_RUNNING"
    MISSION_STATE_PAUSE = "MISSION_STATE_PAUSE"
    MISSION_STATE_ABORT = "MISSION_STATE_ABORT"
    MISSION_STATE_COMPLETE = "MISSION_STATE_COMPLETE"


class PowerMode(Enum):
    POWER_MODE_RUNNING = "POWER_MODE_RUNNING"
    POWER_MODE_STANDBY = "POWER_MODE_STANDBY"
    POWER_MODE_HIBERNATE = "POWER_MODE_HIBERNATE"


class BackToStationReason(Enum):
    BACK_TO_STATION_REASON_NONE = "BACK_TO_STATION_REASON_NONE"
    BACK_TO_STATION_REASON_LOW_BATTERY = "BACK_TO_STATION_REASON_LOW_BATTERY"
    BACK_TO_STATION_REASON_RAINING = "BACK_TO_STATION_REASON_RAINING"
    BACK_TO_STATION_REASON_MOW_MOTOR_OVERHEAT = "BACK_TO_STATION_REASON_MOW_MOTOR_OVERHEAT"
    BACK_TO_STATION_REASON_WHEEL_OVERHEAT = "BACK_TO_STATION_REASON_WHEEL_OVERHEAT"
    BACK_TO_STATION_REASON_NIGHT_TIME = "BACK_TO_STATION_REASON_NIGHT_TIME"


# Missions that count as an active mowing job / a recharge run. Used both
# for the command decision logic here and the activity mapping in the
# lawn mower entity.
MOW_MISSIONS: tuple[Mission, ...] = (
    Mission.MISSION_GLOBAL_CLEAN,
    Mission.MISSION_BUILD_MAP,
    Mission.MISSION_BUILD_MAP_AND_CLEAN,
    Mission.MISSION_TEMPORARY_CLEAN,
    Mission.MISSION_SELECT_REGION_CLEAN,
    Mission.MISSION_DRAW_REGION_CLEAN,
    Mission.MISSION_EDGE_TRIM_CLEAN,
    Mission.MISSION_SCHEDULE_GLOBAL_CLEAN,
    Mission.MISSION_SCHEDULE_BUILD_MAP_AND_CLEAN,
    Mission.MISSION_SCHEDULE_SELECT_REGION_CLEAN,
)

RECHARGE_MISSIONS: tuple[Mission, ...] = (
    Mission.MISSION_RECHARGE,
    Mission.MISSION_BACK_TO_STARTING_POINT,
)


def compute_phase(hub: TerraMowHub, *, connection_error_is_error: bool) -> str:
    """Map the hub's mission state onto a semantic phase string.

    Shared by the lawn-mower activity mapping and the event entity's phase
    detection so the two can never disagree. ``connection_error_is_error``
    is the one intentional difference between them: the lawn mower surfaces
    a lost MQTT connection as its ERROR activity, while the event entity
    ignores it — a dropped connection is routine (mower asleep/docked/after
    a DHCP IP change) and must not fire a spurious error event every cycle.

    Returns one of ``"error"``, ``"mowing"``, ``"paused"``, ``"returning"``
    or ``"docked"``.
    """
    if (connection_error_is_error and hub.connection_error) or hub.has_error:
        return "error"
    if hub.mission_state == MissionState.MISSION_STATE_RUNNING:
        if hub.mission in MOW_MISSIONS:
            if hub.sub_mission == SubMission.SUB_MISSION_FLEXIBLE_STATION_WAIT:
                # Waiting at the base station, equivalent to paused
                return "paused"
            if hub.sub_mission == SubMission.SUB_MISSION_SAVING_MAP:
                # Saving the map, equivalent to finished
                return "docked"
            return "mowing"
        if hub.mission in RECHARGE_MISSIONS:
            return "returning"
        return "docked"
    if hub.mission_state == MissionState.MISSION_STATE_PAUSE:
        return "paused"
    return "docked"


class _MetaFetchChannel:
    """State for one map/path/history-path meta-fetch pipeline.

    The three channels share the exact same seq/etag/retry/pending
    bookkeeping (see ``TerraMowHub._async_handle_meta``); only how the
    fetched data is applied differs (``apply_data``). ``label`` names the
    channel in log messages.
    """

    def __init__(
        self, label: str, apply_data: Callable[[dict[str, Any]], None]
    ) -> None:
        self.label = label
        self.apply_data = apply_data
        self.seq = -1  # highest successfully fetched seq (-1 = none yet)
        self.etag: str | None = None  # ETag for conditional HTTP fetches
        self.pending_meta: dict[str, Any] | None = None  # meta queued during a fetch
        self.retry_meta: dict[str, Any] | None = None  # meta to retry after a failure
        self.retry_count = 0
        self.retry_task: asyncio.Task[Any] | None = None
        self.no_seq_last_fetch = 0.0  # throttle timestamp for seq-less metas
        self.fetching = False  # a fetch for this channel is in flight


class TerraMowHub:
    """Owns the MQTT connection, protocol state and device commands."""

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the hub."""
        self.basic_data = basic_data
        self.host = basic_data.host
        self.password = basic_data.password
        self.hass = hass
        self.mqtt_client: mqtt_client.Client | None = None
        self._stop_event = threading.Event()  # Used to stop the reconnect loop
        self.callbacks: dict[int, list[Callable[..., Any]]] = {}  # Stores dp_id and its list of callback functions
        self.map_callbacks: list[Callable[..., Any]] = []  # Stores map info callback functions
        self.pose_callbacks: list[Callable[..., Any]] = []  # Stores pose callback functions
        self.path_callbacks: list[Callable[..., Any]] = []  # Stores path data callback functions
        self.history_path_callbacks: list[Callable[..., Any]] = []  # Stores history path data callback functions
        self._state_listeners: list[Callable[[], None]] = []  # State change listeners (connection state, dp_107, model)
        self.connection_error = False  # Whether the MQTT connection is in an error state
        self._pending_serial: str | None = None  # dp_102 serial parked during entry setup
        self._map_info: dict[str, Any] = {}  # Stores the current map info
        self._map_data: dict[str, Any] = {}  # Stores map data fetched over HTTP
        self._path_data: dict[str, Any] = {}  # Stores path data fetched over HTTP
        self._history_path_data: dict[str, Any] = {}  # Stores history path data fetched over HTTP
        self._pose: dict[str, Any] = {}  # Stores the real-time pose
        # One meta-fetch channel per HTTP-backed resource; each bundles the
        # seq/etag/retry/pending bookkeeping for its meta topic.
        self._map_channel = _MetaFetchChannel("map", self._apply_map_data)
        self._path_channel = _MetaFetchChannel("path", self._apply_path_data)
        self._history_path_channel = _MetaFetchChannel(
            "history path", self._apply_history_path_data
        )
        self._meta_channels: tuple[_MetaFetchChannel, ...] = (
            self._map_channel,
            self._path_channel,
            self._history_path_channel,
        )
        self._meta_topic_channels: dict[str, _MetaFetchChannel] = {
            MAP_META_TOPIC: self._map_channel,
            PATH_META_TOPIC: self._path_channel,
            PATH_HISTORY_META_TOPIC: self._history_path_channel,
        }
        self._no_seq_min_interval = 5.0
        self._global_params: dict[str, Any] = {}  # Stores dp_155 global work parameters
        self._map_status: dict[str, Any] = {}  # Stores dp_117 map status
        self._current_work_data: dict[str, Any] = {}  # Stores dp_113 current work data
        self._statistics_data: dict[str, Any] = {}  # Stores dp_124 work statistics data
        self._base_station_time: dict[str, Any] = {}  # Stores dp_125 base station usage time
        self._blade_time: dict[str, Any] = {}  # Stores dp_126 blade usage time
        self._schedule_data: dict[str, Any] = {}  # Stores dp_138 upcoming schedule
        self._battery_status: dict[str, Any] = {}  # Store dp_108 battery status
        self._battery_level: int | None = None  # Store dp_8 battery percentage
        self._robot_info: dict[str, Any] = {}  # Store dp_102 device/network info
        self._component_versions: dict[str, Any] = {}  # Store dp_129 component firmware versions
        self._error_list: list[Any] = []  # Store dp_116 active error list
        self._event_list: list[Any] = []  # Store dp_123 event log
        self._cellular_info: dict[str, Any] = {}  # Store dp_135 cellular/4G info
        self._environment_info: dict[str, Any] = {}  # Store dp_152 environment/status
        self._weather_info: dict[str, Any] = {}  # Store dp_157 extreme-weather warning
        self._operating_modes: dict[str, Any] = {}  # Store dp_154 operating modes
        self._advanced_settings: dict[str, Any] = {}  # Store dp_150 advanced settings
        self._full_schedule: dict[str, Any] = {}  # Store dp_122 full weekly schedule list
        self._state_flag_134: dict[str, Any] = {}  # Store dp_134 undecoded binary flag
        self._map_save_progress: dict[str, Any] = {}  # Store dp_118 map-save progress %
        self._task_status: dict[str, Any] = {}  # Store dp_107 task status raw payload
        self._seen_unknown_dp_ids: set[int] = set()  # Unknown data points already logged
        # Bounded per-dp change history (epoch, payload) for undocumented dps, so
        # a single diagnostics export reveals how dynamic values move over time.
        self._unknown_dp_history: dict[int, deque[tuple[float, str]]] = {}
        # Latest raw payload seen for each unhandled data point, surfaced in
        # diagnostics so undocumented dps can be identified from real data.
        self._unknown_dp_payloads: dict[int, str] = {}
        self._device_model: str = "TerraMow S1200"  # Default model name, kept for backward compatibility
        # Entities reach the hub through this attribute; the name is kept
        # from the time the lawn mower entity itself played the hub role.
        self.basic_data.lawn_mower = self

        # Robot state
        self.mission = Mission.MISSION_IDLE
        self.sub_mission = SubMission.SUB_MISSION_IDLE
        self.mission_state = MissionState.MISSION_STATE_IDLE
        self._is_robot_navi_located: bool | None = None
        self._is_upgrading: bool | None = None
        self._power_mode: str | None = None

        # dp_119 command acknowledgements: confirmed commands park a future
        # here keyed by their seq; on_command_ack resolves it with the code.
        # Only touched from the event loop.
        self._pending_acks: dict[int, asyncio.Future[int]] = {}
        self._last_command_ack: dict[str, Any] = {}  # Last dp_119 ack (diagnostics)
        # Captured app-direction writes (epoch, topic, payload) — source
        # material for documenting undocumented write formats (schedule etc.).
        self._app_dp_captures: deque[tuple[float, str, str]] = deque(maxlen=50)

        self.cmd_seq = random.randint(0, 0xFFFFFFFF)  # Generate a random command sequence number
        # get_cmd_seq is reachable from the paho network thread (compatibility
        # request on connect) and from executor threads (sync command senders),
        # so the increment must be atomic to avoid handing out a duplicate seq.
        self._cmd_seq_lock = threading.Lock()

        self._control_interval = 1.0  # Control interval time
        # Start outside the rate-limit window so the first command after a
        # (re)load is accepted instead of erroring for a second.
        self._last_control_time = time.monotonic() - self._control_interval

        _LOGGER.debug("TerraMowHub created with host %s", self.host)

    @property
    def device_model(self) -> str:
        """Return the device model."""
        return self._device_model

    @device_model.setter
    def device_model(self, model_name: str) -> None:
        """Update the device model."""
        self._device_model = model_name

    def diagnostics_snapshot(self) -> dict[str, Any]:
        """Return copies of the unknown-dp bookkeeping for the diagnostics export.

        The MQTT worker thread appends to these structures; handing out
        copies keeps the export from iterating live objects (a deque mutated
        during iteration raises RuntimeError).
        """
        return {
            "seen_unknown_dp_ids": sorted(self._seen_unknown_dp_ids),
            "unknown_dp_payloads": dict(self._unknown_dp_payloads),
            "unknown_dp_history": {
                dp_id: list(history)
                for dp_id, history in list(self._unknown_dp_history.items())
            },
            "last_command_ack": dict(self._last_command_ack),
            "app_dp_captures": list(self._app_dp_captures),
        }

    def register_state_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a listener called on connection/dp_107/model changes.

        Listeners may be invoked from the MQTT worker thread, so they must
        be thread-safe (e.g. use ``schedule_update_ha_state``).

        Returns an idempotent unsubscribe callable removing the listener.
        """
        self._state_listeners.append(listener)
        return _make_unsubscriber(self._state_listeners, listener)

    def _notify_state_listeners(self) -> None:
        """Notify listeners about a state change."""
        # Iterate over a snapshot: listeners are registered from the event loop
        # while this runs on the MQTT worker thread, so iterating the live list
        # can raise "list changed size during iteration".
        for listener in list(self._state_listeners):
            try:
                listener()
            except Exception as e:
                _LOGGER.error("Error in hub state listener: %s", e)

    def _set_connection_error(self, value: bool) -> None:
        """Track the MQTT connection state and notify on changes."""
        if self.connection_error != value:
            self.connection_error = value
            self._notify_state_listeners()

    def _dispatch(self, target: Callable[..., Any], *args: Any) -> None:
        """Schedule a handler onto the Home Assistant event loop from any thread.

        The MQTT worker thread must never touch loop-bound APIs directly;
        the deprecated ``hass.add_job`` used to provide this bridge.
        Coroutine functions become tasks on the loop; plain callables run
        directly. ``call_soon_threadsafe`` is also safe when already called
        from the loop thread.
        """

        def _run_on_loop() -> None:
            try:
                if asyncio.iscoroutinefunction(target):
                    self.hass.async_create_task(target(*args))
                else:
                    target(*args)
            except Exception as err:
                _LOGGER.error("Error dispatching %s: %s", target, err)

        self.hass.loop.call_soon_threadsafe(_run_on_loop)

    def _dispatch_batch(
        self, targets: list[Callable[..., Any]], *args: Any
    ) -> None:
        """Schedule a snapshot of handlers onto the event loop in one hop.

        A data point like dp_107 fans out to a dozen entity callbacks; one
        ``call_soon_threadsafe`` per callback costs a loop wakeup each.
        Batching keeps the exact per-callback semantics of ``_dispatch``
        (registration order, coroutine handlers become tasks in that order,
        one handler's error never stops the next) at a single hop.
        """
        if not targets:
            return

        def _run_on_loop() -> None:
            for target in targets:
                try:
                    if asyncio.iscoroutinefunction(target):
                        self.hass.async_create_task(target(*args))
                    else:
                        target(*args)
                except Exception as err:
                    _LOGGER.error("Error dispatching %s: %s", target, err)

        self.hass.loop.call_soon_threadsafe(_run_on_loop)

    def _can_accept_command(self) -> bool:
        """Check if control commands can be accepted"""
        now = time.monotonic()
        if now - self._last_control_time < self._control_interval:
            _LOGGER.info("Request too quick, skip it")
            return False
        self._last_control_time = now
        return True

    def _ensure_command_allowed(self) -> None:
        """Raise if a command arrives within the rate-limit window.

        Two commands less than ``_control_interval`` apart would otherwise be
        dropped silently, so the caller (and Home Assistant) never learns the
        command did not reach the mower. Surfacing it lets the automation retry.
        """
        if not self._can_accept_command():
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rate_limited",
            )

    def start(self) -> None:
        """Start the MQTT client in a separate thread."""
        _LOGGER.info("Starting MQTT client, connecting to %s:%d", self.host, MQTT_PORT)
        _LOGGER.debug("MQTT connection params: username=%s", MQTT_USERNAME)

        self.mqtt_client = create_mqtt_client()
        self.mqtt_client.username_pw_set(MQTT_USERNAME, self.password)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message

        # Register the hub's own dp handlers before the network thread starts,
        # so retained messages delivered right after connect cannot arrive
        # ahead of registration and be misfiled as undocumented data points.
        self.register_all_callbacks()

        # Start MQTT loop thread
        _LOGGER.debug("Starting MQTT thread")
        self.mqtt_thread = threading.Thread(target=self.mqtt_loop)
        self.mqtt_thread.daemon = True
        self.mqtt_thread.start()

        _LOGGER.debug("MQTT client startup completed")

    async def async_stop(self) -> None:
        """Stop the MQTT client and clean up resources."""
        _LOGGER.info("Stopping MQTT client")
        self._stop_event.set()
        for channel in self._meta_channels:
            self._reset_meta_retry(channel)
        self._reset_pending_meta()
        if self.mqtt_client:
            # disconnect() makes loop_forever() return so the worker thread can
            # see the stop event and exit.
            self.mqtt_client.disconnect()
        # Wait for the worker thread to actually finish, to avoid leaving a
        # zombie thread behind after a reload/reconfigure (which would keep
        # reconnecting and flooding the log). Join in the executor so we don't
        # block the event loop.
        thread = getattr(self, "mqtt_thread", None)
        if thread is not None and thread.is_alive():
            await self.hass.async_add_executor_job(thread.join, MQTT_THREAD_JOIN_TIMEOUT)
            if thread.is_alive():
                _LOGGER.warning(
                    "MQTT worker thread did not stop within %ds", MQTT_THREAD_JOIN_TIMEOUT
                )

    def register_all_callbacks(self) -> None:
        """Register all callbacks for data points."""
        self.register_callback(107, self.on_mission_status)
        self.register_callback(155, self.on_global_params)
        self.register_callback(117, self.on_map_status)
        self.register_callback(113, self.on_current_work_data)
        self.register_callback(124, self.on_statistics_data)
        self.register_callback(125, self.on_base_station_time)
        self.register_callback(126, self.on_blade_time)
        self.register_callback(138, self.on_schedule_data)
        self.register_callback(108, self.on_battery_status)
        self.register_callback(8, self.on_battery_level)
        self.register_callback(102, self.on_device_info)
        self.register_callback(129, self.on_component_versions)
        self.register_callback(116, self.on_error_list)
        self.register_callback(123, self.on_event_data)
        self.register_callback(135, self.on_cellular_info)
        self.register_callback(152, self.on_environment_info)
        self.register_callback(157, self.on_weather_info)
        self.register_callback(154, self.on_operating_modes)
        self.register_callback(122, self.on_full_schedule)
        self.register_callback(134, self.on_state_flag_134)
        self.register_callback(118, self.on_map_save_progress)
        self.register_callback(150, self.on_advanced_settings)
        self.register_callback(COMMAND_ACK_DP, self.on_command_ack)
        self.register_callback(COMPATIBILITY_INFO_DP, self.on_compatibility_info)

    async def on_global_params(self, payload: str) -> None:
        """Handle global parameter updates (dp_155)."""
        _LOGGER.debug("Raw global params payload: %s", payload)
        try:
            data = json.loads(payload)
            old_params = self._global_params
            self._global_params = data
            _LOGGER.debug("Global parameters updated: %s", data)

            # Check whether the main direction mode changed and notify the mode selector
            self._notify_mode_selector_if_changed(old_params, data)

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_155: %s", payload)

    def _notify_mode_selector_if_changed(self, old_params: dict[str, Any], new_params: dict[str, Any]) -> None:
        """Notify the mode selector if the main direction mode changed."""
        try:
            old_mode = old_params.get('main_direction_angle_config', {}).get('mode') if old_params else None
            new_mode = new_params.get('main_direction_angle_config', {}).get('mode')

            if new_mode and old_mode != new_mode:
                _LOGGER.debug("Main direction mode changed from %s to %s, notifying mode selector", old_mode, new_mode)

                # Notify the mode selector via a Home Assistant event
                self.hass.bus.fire(f"{DOMAIN}_device_mode_confirmed", {
                    "device_host": self.host,
                    "confirmed_mode": new_mode,
                    "old_mode": old_mode,
                    "source": "device_feedback"
                })

        except Exception as e:
            _LOGGER.warning("Error notifying mode selector: %s", e)

    async def on_map_status(self, payload: str) -> None:
        """Handle map status updates (dp_117)."""
        _LOGGER.debug("Raw map status payload: %s", payload)
        try:
            data = json.loads(payload)
            self._map_status = data
            _LOGGER.debug("Map status updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_117: %s", payload)

    async def on_current_work_data(self, payload: str) -> None:
        """Handle current work data updates (dp_113)."""
        _LOGGER.debug("Raw current work data payload: %s", payload)
        try:
            data = json.loads(payload)
            self._current_work_data = data
            _LOGGER.debug("Current work data updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_113: %s", payload)

    async def on_statistics_data(self, payload: str) -> None:
        """Handle statistics data updates (dp_124)."""
        _LOGGER.debug("Raw statistics data payload: %s", payload)
        try:
            data = json.loads(payload)
            self._statistics_data = data
            _LOGGER.debug("Statistics data updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_124: %s", payload)

    async def on_base_station_time(self, payload: str) -> None:
        """Handle base station time updates (dp_125)."""
        _LOGGER.debug("Raw base station time payload: %s", payload)
        try:
            data = json.loads(payload)
            self._base_station_time = data
            _LOGGER.debug("Base station time updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_125: %s", payload)
            return
        if self.basic_data.entry_id is not None:
            async_sync_base_station_maintenance_issue(
                self.hass, self.basic_data.entry_id, data
            )

    async def on_blade_time(self, payload: str) -> None:
        """Handle blade time updates (dp_126)."""
        _LOGGER.debug("Raw blade time payload: %s", payload)
        try:
            data = json.loads(payload)
            self._blade_time = data
            _LOGGER.debug("Blade time updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_126: %s", payload)
            return
        if self.basic_data.entry_id is not None:
            async_sync_blade_maintenance_issue(
                self.hass, self.basic_data.entry_id, data
            )

    async def on_schedule_data(self, payload: str) -> None:
        """Handle schedule data updates (dp_138)."""
        _LOGGER.debug("Raw schedule data payload: %s", payload)
        try:
            data = json.loads(payload)
            self._schedule_data = data
            _LOGGER.debug("Schedule data updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_138: %s", payload)

    async def on_battery_level(self, payload: str) -> None:
        """Handle battery level updates (dp_8, battery percentage)."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_8: %s", payload)
            return
        value = data.get("int_value")
        if isinstance(value, int) and not isinstance(value, bool):
            self._battery_level = value

    async def on_device_info(self, payload: str) -> None:
        """Handle device/network info updates (dp_102).

        Carries the real firmware version the TerraMow app shows (``version``),
        plus serial/network identifiers. The version is surfaced to Home
        Assistant and the serial (``sn``) is adopted as the stable device
        identity; everything else stays private (and the serial is redacted
        from diagnostics exports).
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_102: %s", payload)
            return
        if isinstance(data, dict):
            self._robot_info = data
            version = data.get("version")
            if isinstance(version, str) and version:
                self._dispatch(self._async_update_device_sw_version, version)
            serial = data.get("sn")
            if isinstance(serial, str) and serial:
                self._dispatch(self._async_adopt_serial, serial)

    async def on_component_versions(self, payload: str) -> None:
        """Handle per-component firmware version updates (dp_129)."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_129: %s", payload)
            return
        if isinstance(data, dict):
            self._component_versions = data

    async def on_error_list(self, payload: str) -> None:
        """Handle the active-error list (dp_116, undocumented).

        Payload observed as ``{"error_list": [...]}``. Parsed defensively; the
        entry structure is unknown (empty on the reference device).
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_116: %s", payload)
            return
        if isinstance(data, dict):
            errors = data.get("error_list")
            if isinstance(errors, list):
                self._error_list = errors

    async def on_event_data(self, payload: str) -> None:
        """Handle the event log (dp_123, undocumented).

        Payload observed as ``{"event_list": [{"code": int, "time": str}]}``.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_123: %s", payload)
            return
        if isinstance(data, dict):
            events = data.get("event_list")
            if isinstance(events, list):
                self._event_list = events

    async def on_cellular_info(self, payload: str) -> None:
        """Handle cellular/4G modem info (dp_135, undocumented).

        Observed as ``{"is_enabled":bool,"RSRP":int,"RSRQ":int,"type":str,…}``.
        Only present on models with a cellular modem; parsed defensively.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_135: %s", payload)
            return
        if isinstance(data, dict):
            self._cellular_info = data

    async def on_environment_info(self, payload: str) -> None:
        """Handle environment/status info (dp_152, undocumented).

        Observed as ``{"is_defogger_heating":bool,"is_illuminate_light_on":bool,
        "sunrise":{"hour":int,"minute":int},"sunset":{…},
        "is_not_in_daylight_period":bool,"manual_mapping":{…}}``.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_152: %s", payload)
            return
        if isinstance(data, dict):
            self._environment_info = data

    async def on_weather_info(self, payload: str) -> None:
        """Handle the extreme-weather warning (dp_157, undocumented).

        Observed as ``{"has_extream_weather":bool,"extream_weather_info_url":str}``
        (note the device's spelling of "extream").
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_157: %s", payload)
            return
        if isinstance(data, dict):
            self._weather_info = data

    async def on_full_schedule(self, payload: str) -> None:
        """Handle the full weekly schedule (dp_122, undocumented).

        Only ``SCHEDULE_CMD_TYPE_GET`` responses carry a ``schedule_list``; the
        ADD/DELETE acknowledgements do not, so only a payload that actually
        contains a schedule list updates the cache. The device does not push
        this on its own — it is requested via ``_request_full_schedule``.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_122: %s", payload)
            return
        if isinstance(data, dict):
            schedule_list = data.get("schedule_list")
            if isinstance(schedule_list, dict):
                self._full_schedule = schedule_list

    async def on_state_flag_134(self, payload: str) -> None:
        """Handle the undecoded binary flag (dp_134, undocumented).

        Observed as ``{"enum_value":0|1}`` toggling during operation. The
        meaning is unknown; the raw payload is cached so a diagnostic binary
        sensor can surface it for decoding.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_134: %s", payload)
            return
        if isinstance(data, dict):
            self._state_flag_134 = data

    async def on_map_save_progress(self, payload: str) -> None:
        """Handle the map-save / upload progress (dp_118, undocumented).

        Observed as ``{"int_value":0..100}`` ramping while the device saves the
        map after a mow (``SUB_MISSION_SAVING_MAP`` / "map is being saved"). The
        raw payload is cached so a progress sensor can surface it.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_118: %s", payload)
            return
        if isinstance(data, dict):
            self._map_save_progress = data

    async def on_operating_modes(self, payload: str) -> None:
        """Handle the operating-mode triple (dp_154, undocumented).

        Observed as ``{"move_mode":str,"map_mode":str,"mow_mode":str}``.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_154: %s", payload)
            return
        if isinstance(data, dict):
            self._operating_modes = data

    async def on_advanced_settings(self, payload: str) -> None:
        """Handle the advanced settings block (dp_150, undocumented).

        Observed as nested ``{"enable_cliff_detection":{"value":bool},
        "rain_sensor_threshold":{"upper_limit":int},"after_rain_stop_setting":{…},
        …}``. Surfaced read-only; parsed defensively.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_150: %s", payload)
            return
        if isinstance(data, dict):
            self._advanced_settings = data

    async def on_battery_status(self, payload: str) -> None:
        """Handle battery status updates (dp_108)."""
        _LOGGER.debug("Raw battery status payload: %s", payload)
        try:
            data = json.loads(payload)
            self._battery_status = data
            _LOGGER.debug("Battery status updated: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload for dp_108: %s", payload)

    async def on_mission_status(self, payload: str) -> None:
        """Handle mission status updates."""
        _LOGGER.debug("Raw mission status payload: %s", payload)
        try:
            data = json.loads(payload)
            _LOGGER.debug("Received mission status: %s", data)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON payload: %s", payload)
            return

        # Preserve the raw payload so that downstream entities can read fields
        # like has_error / back_to_station_reason without enum conversion.
        self._task_status = dict(data)

        # Define a mapping from field names to enum classes
        enum_mapping = {
            "mission": Mission,
            "sub_mission": SubMission,
            "state": MissionState,
            "power_mode": PowerMode,
            "back_to_station_reason": BackToStationReason
        }

        # Capture raw fields before enum conversion mutates the dict
        if "is_robot_navi_located" in data:
            self._is_robot_navi_located = data.get("is_robot_navi_located")
        if "is_upgrading" in data:
            self._is_upgrading = data.get("is_upgrading")
        if "power_mode" in data:
            self._power_mode = data.get("power_mode")

        # Convert enum strings to enum members
        for key, enum_class in enum_mapping.items():
            if key in data:
                old_value = data[key]
                try:
                    data[key] = enum_class(data[key])
                    _LOGGER.debug("Converted %s: %s -> %s", key, old_value, data[key])
                except (ValueError, KeyError) as e:
                    _LOGGER.error("Invalid value for %s: %s (error: %s)", key, data[key], e)
                    # Unknown value (e.g. newer firmware): drop the key so the
                    # .get(...) fallbacks below keep the previous known state
                    # instead of clobbering it with None.
                    del data[key]

        # Store old values for logging
        old_mission = self.mission
        old_sub_mission = self.sub_mission
        old_mission_state = self.mission_state

        self.mission = data.get("mission", self.mission)
        self.sub_mission = data.get("sub_mission", self.sub_mission)
        self.mission_state = data.get("state", self.mission_state)

        _LOGGER.debug("Mission state updated: mission=%s->%s, sub_mission=%s->%s, state=%s->%s, has_error=%s, back_to_station_reason=%s",
                     old_mission, self.mission, old_sub_mission, self.sub_mission,
                     old_mission_state, self.mission_state, self.has_error, self.back_to_station_reason)

        self._notify_state_listeners()

    async def on_command_ack(self, payload: str) -> None:
        """Handle a dp_119 command acknowledgement.

        The device echoes a command's ``seq`` with ``code`` 0 (OK) or an
        error code. Confirmed commands (``async_publish_with_ack``) wait on
        a parked future; anything else is bookkeeping — rejected
        fire-and-forget commands are surfaced as a warning so failures are
        at least visible in the log.
        """
        try:
            data = json.loads(payload)
            seq = int(data.get("seq", -1))
            code = int(data.get("code", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            _LOGGER.warning("Invalid dp_119 command ack payload: %s", payload[:200])
            return
        self._last_command_ack = {"seq": seq, "code": code}
        future = self._pending_acks.pop(seq, None)
        if future is not None:
            if not future.done():
                future.set_result(code)
        elif code != 0:
            _LOGGER.warning(
                "Device rejected command seq=%s with code=%s", seq, code
            )

    @property
    def last_command_ack(self) -> dict[str, Any]:
        """Get the last dp_119 command acknowledgement (for diagnostics)."""
        return self._last_command_ack

    async def async_publish_with_ack(
        self, dp_id: int, data: dict[str, Any], timeout: float = COMMAND_ACK_TIMEOUT
    ) -> int | None:
        """Publish a command and wait for its dp_119 acknowledgement.

        Returns the ack code (0 = OK) or ``None`` when no ack arrived within
        the timeout — older firmware doesn't ack every command, so a missing
        ack keeps the optimistic fire-and-forget semantics. A non-zero code
        raises a translated ``HomeAssistantError`` so service calls report
        the device's rejection instead of silently "succeeding".

        Must be called from the event loop; ``data`` must carry a ``seq``.
        """
        seq = int(data["seq"])
        future: asyncio.Future[int] = self.hass.loop.create_future()
        self._pending_acks[seq] = future
        try:
            self.publish_data_point(dp_id, data)
            code = await asyncio.wait_for(future, timeout)
        except TimeoutError:
            _LOGGER.debug(
                "No dp_119 ack for command seq=%s within %.1fs; assuming ok",
                seq,
                timeout,
            )
            return None
        finally:
            self._pending_acks.pop(seq, None)
        if code != 0:
            _LOGGER.warning(
                "Device rejected command dp_%s seq=%s with code=%s",
                dp_id,
                seq,
                code,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"code": str(code)},
            )
        return code

    async def on_compatibility_info(self, payload: str) -> None:
        """Handle compatibility info updates (dp_127)."""
        _LOGGER.debug("Raw compatibility info payload: %s", payload)
        try:
            data = json.loads(payload)
            _LOGGER.debug("Received version compatibility info: %s", data)

            # Perform the version compatibility check
            compatibility_status = self.basic_data.check_version_compatibility(data)
            self.basic_data.compatibility_status = compatibility_status
            self.basic_data.firmware_version = data

            # Show the firmware version on the device page. Prefer the real
            # version from dp_102 (e.g. "9.9.210"); the dp_127 compatibility
            # number ("28.3") is only a fallback until dp_102 has arrived.
            sw_version = self.firmware_version_name or self._format_firmware_version(data)
            if sw_version:
                self._dispatch(self._async_update_device_sw_version, sw_version)

            # Log the compatibility check result
            message = self.basic_data.get_compatibility_message()
            if compatibility_status == CompatibilityStatus.COMPATIBLE:
                _LOGGER.info("Version compatibility check: %s", message)
            else:
                _LOGGER.warning("Version compatibility check: %s", message)

            # If the version is incompatible, consider disabling some features or showing a warning
            if compatibility_status == CompatibilityStatus.INCOMPATIBLE:
                _LOGGER.error("Version completely incompatible, recommend checking firmware and plugin versions")

            # Sync the compatibility result to a Home Assistant Repair Issue so
            # that incompatible firmware surfaces as an actionable repair card
            # rather than just a sensor.
            if self.basic_data.entry_id is not None:
                async_sync_compatibility_issue(
                    self.hass, self.basic_data.entry_id, self.basic_data
                )

        except json.JSONDecodeError:
            _LOGGER.error("Failed to parse compatibility info JSON: %s", payload)
        except Exception as e:
            _LOGGER.error("Error processing version compatibility info: %s", e)

    def mqtt_loop(self) -> None:
        """MQTT main loop with auto-reconnect.

        Uses exponential backoff and throttled logging so an unreachable
        mower (asleep, docked, or after a DHCP IP change) does not flood
        the log with an ERROR every few seconds or hammer the network.
        The wait is interruptible via ``_stop_event`` so shutdown is
        immediate when the hub is stopped.
        """
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                if self.mqtt_client and not self.mqtt_client.is_connected():
                    _LOGGER.info("Attempting to connect to MQTT Broker %s", self.host)
                    self.mqtt_client.connect(self.host, MQTT_PORT, 60)
                    _LOGGER.info("Connected to MQTT Broker")
                consecutive_failures = 0
                if self.mqtt_client:
                    self.mqtt_client.loop_forever()
            except Exception as e:
                consecutive_failures += 1
                # Warn once on the first failure, then drop to DEBUG to avoid flooding the log.
                if consecutive_failures == 1:
                    _LOGGER.warning(
                        "Cannot reach TerraMow MQTT broker at %s:%d (%s); "
                        "will keep retrying with backoff",
                        self.host, MQTT_PORT, e,
                    )
                else:
                    _LOGGER.debug(
                        "MQTT connection still failing (attempt %d): %s",
                        consecutive_failures, e,
                    )
                # Set the error state
                self._set_connection_error(True)
                # Exponential backoff capped at MQTT_RECONNECT_MAX_DELAY; use an interruptible wait so we can stop immediately.
                delay = min(
                    MQTT_RECONNECT_BASE_DELAY * (2 ** (consecutive_failures - 1)),
                    MQTT_RECONNECT_MAX_DELAY,
                )
                self._stop_event.wait(delay)

    def on_mqtt_connect(self, client: Any, _userdata: Any, _flags: Any, rc: int) -> None:
        """Callback when connected to MQTT Broker."""
        if rc == 0:
            _LOGGER.info("MQTT connected")
            # One wildcard subscription covers every data point, including ids
            # above the historical 0-200 range; the regex dispatcher in
            # on_mqtt_message already handles arbitrary ids.
            client.subscribe("data_point/+/robot")
            # Capture app-direction writes: the vendor app's schedule
            # ADD/DELETE payloads (and their carrier data point) are
            # undocumented; recording this traffic is how the write format
            # gets reverse-engineered from real app usage. Includes echoes of
            # our own commands — those are useful reference samples.
            client.subscribe(APP_DP_TOPIC_FILTER)
            # Subscribe to the map info topic (for older firmware compatibility)
            client.subscribe(MAP_INFO_TOPIC)
            _LOGGER.debug("Subscribed to %s topic", MAP_INFO_TOPIC)

            # Subscribe to map/path meta data and pose
            client.subscribe(MAP_META_TOPIC)
            client.subscribe(PATH_META_TOPIC)
            client.subscribe(PATH_HISTORY_META_TOPIC)
            client.subscribe(POSE_TOPIC)
            _LOGGER.debug(
                "Subscribed to %s/%s/%s/%s topic",
                MAP_META_TOPIC,
                PATH_META_TOPIC,
                PATH_HISTORY_META_TOPIC,
                POSE_TOPIC,
            )

            # Subscribe to the device model topic
            client.subscribe(MODEL_NAME_TOPIC)
            _LOGGER.debug("Subscribed to %s topic", MODEL_NAME_TOPIC)

            # Proactively request version compatibility information
            self._request_compatibility_info()
            # Proactively request the full weekly schedule (dp_122 is only sent
            # in response to a GET; without this the schedule calendar is empty)
            self._request_full_schedule()

            self.connection_error = False
            self._notify_state_listeners()
        else:
            _LOGGER.error(f"MQTT connection failed with code {rc}")
            # Set the error state
            self._set_connection_error(True)

    def on_mqtt_disconnect(self, _client: Any, _userdata: Any, rc: int) -> None:
        """Callback when disconnected from MQTT Broker."""
        if rc != 0:
            _LOGGER.warning(f"Unexpected MQTT disconnection: {rc}")
            # Automatically reconnect after a disconnection
            # Set the error state
            self._set_connection_error(True)

    def on_mqtt_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        """Callback when a message is received."""
        topic = msg.topic
        try:
            payload = msg.payload.decode()
        except UnicodeDecodeError:
            # A raising on_message callback propagates out of loop_forever(),
            # which the reconnect loop treats as a connection failure; a
            # retained undecodable payload would then wedge the connection in
            # a reconnect/redeliver cycle. Drop the message instead.
            _LOGGER.warning("Ignoring undecodable MQTT payload on topic %s", topic)
            return

        if topic != POSE_TOPIC:
            _LOGGER.debug("Received MQTT message: topic=%s, payload=%s", topic, payload)

        # Handle map / path / history path meta info
        channel = self._meta_topic_channels.get(topic)
        if channel is not None:
            try:
                meta = json.loads(payload)
                self._dispatch(self._async_handle_meta, channel, meta)
            except json.JSONDecodeError:
                _LOGGER.error(
                    "Failed to parse %s meta JSON: %s", channel.label, payload[:200]
                )
            except Exception as e:
                _LOGGER.error("Error handling %s meta: %s", channel.label, e)
            return

        # Handle the real-time pose
        if topic == POSE_TOPIC:
            try:
                pose = json.loads(payload)
                self._pose = pose
                # Snapshot: entities append callbacks from the event loop while
                # this runs on the MQTT worker thread.
                self._dispatch_batch(list(self.pose_callbacks), pose)
            except json.JSONDecodeError:
                _LOGGER.error("Failed to parse pose JSON: %s", payload[:200])
            except Exception as e:
                _LOGGER.error("Error handling pose: %s", e)
            return

        # App-direction data-point traffic (vendor app commands, plus echoes
        # of our own). Logged and kept (bounded) for the diagnostics export so
        # undocumented write formats can be captured from real app usage.
        if APP_TOPIC_PATTERN.fullmatch(topic):
            _LOGGER.debug("Observed app-direction message %s: %s", topic, payload)
            self._app_dp_captures.append((time.time(), topic, payload))
            return

        # Handle the map info topic
        if topic == MAP_INFO_TOPIC:
            _LOGGER.debug("Received map info message, size: %d bytes", len(payload))
            self._handle_map_info(payload)
            return

        # Handle the device model topic
        if topic == MODEL_NAME_TOPIC:
            _LOGGER.debug("Received device model message: %s", payload)
            self._handle_model_name(payload)
            return

        # Parse the data_point topic using a regular expression
        match = TOPIC_PATTERN.fullmatch(topic)
        if not match:
            _LOGGER.warning("Invalid topic format: %s", topic)
            return

        try:
            dp_id = int(match.group(1))
            _LOGGER.debug("Parsed dp_id: %d from topic: %s", dp_id, topic)
        except ValueError:  # pragma: no cover - regex guarantees \d+ parses
            _LOGGER.warning("Invalid dp_id in topic: %s", topic)
            return

        # Call the corresponding callback functions
        callbacks = self.callbacks.get(dp_id)
        if callbacks:
            _LOGGER.debug("Calling %d callbacks for dp_id %d", len(callbacks), dp_id)
            self._dispatch_batch(list(callbacks), payload)
        else:
            # Help discover undocumented data points (e.g. lift alarms, schedule
            # switches, error codes): each unknown dp_id is logged once at INFO,
            # while the full payload is continuously logged at DEBUG. The latest
            # payload is also kept for the diagnostics export so undocumented
            # dps can be identified from real data without live log capture.
            truncated = payload[:500]
            self._unknown_dp_payloads[dp_id] = truncated
            # Record a timestamped trace of *changes* (skip repeats) so a chatty
            # heartbeat cannot evict the real transitions we want to decode.
            history = self._unknown_dp_history.get(dp_id)
            if history is None:
                history = deque(maxlen=UNKNOWN_DP_HISTORY_MAXLEN)
                self._unknown_dp_history[dp_id] = history
            if not history or history[-1][1] != truncated:
                history.append((time.time(), truncated))
            if dp_id not in self._seen_unknown_dp_ids:
                self._seen_unknown_dp_ids.add(dp_id)
                _LOGGER.info(
                    "Received undocumented data point %d (no handler registered). "
                    "First payload: %s. Enable debug logging for the terramow "
                    "integration to record all payloads for this data point.",
                    dp_id, payload[:500],
                )
            elif _LOGGER.isEnabledFor(logging.DEBUG):
                # Guarded: the slice would otherwise run per message even
                # with debug logging off.
                _LOGGER.debug("Unhandled data point %d payload: %s", dp_id, payload[:2000])

    def register_callback(
        self, dp_id: int, callback: Callable[..., Any]
    ) -> Callable[[], None]:
        """Register a callback function for a specific dp_id.

        Returns an idempotent unsubscribe callable removing the callback.
        """
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        if dp_id not in self.callbacks:
            self.callbacks[dp_id] = []
        self.callbacks[dp_id].append(callback)
        _LOGGER.debug(f"Callback registered for dp_id: {dp_id}")
        return _make_unsubscriber(self.callbacks[dp_id], callback)

    def register_map_callback(self, callback: Callable[..., Any]) -> Callable[[], None]:
        """Register a callback function for map info updates.

        Returns an idempotent unsubscribe callable removing the callback.
        """
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.map_callbacks.append(callback)
        _LOGGER.debug("Map callback registered")
        # If map data already exists, trigger the callback immediately
        if self._map_info:
            self._dispatch(callback, self._map_info)
        return _make_unsubscriber(self.map_callbacks, callback)

    def register_pose_callback(self, callback: Callable[..., Any]) -> Callable[[], None]:
        """Register a callback function for pose updates.

        Returns an idempotent unsubscribe callable removing the callback.
        """
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.pose_callbacks.append(callback)
        _LOGGER.debug("Pose callback registered")
        if self._pose:
            self._dispatch(callback, self._pose)
        return _make_unsubscriber(self.pose_callbacks, callback)

    def register_path_callback(self, callback: Callable[..., Any]) -> Callable[[], None]:
        """Register a callback function for path data updates.

        Returns an idempotent unsubscribe callable removing the callback.
        """
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.path_callbacks.append(callback)
        _LOGGER.debug("Path callback registered")
        if self._path_data:
            self._dispatch(callback, self._path_data)
        return _make_unsubscriber(self.path_callbacks, callback)

    def register_history_path_callback(
        self, callback: Callable[..., Any]
    ) -> Callable[[], None]:
        """Register a callback function for history path data updates.

        Returns an idempotent unsubscribe callable removing the callback.
        """
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.history_path_callbacks.append(callback)
        _LOGGER.debug("History path callback registered")
        if self._history_path_data:
            self._dispatch(callback, self._history_path_data)
        return _make_unsubscriber(self.history_path_callbacks, callback)

    def _update_map_info(self, map_info: dict[str, Any]) -> None:
        """Update map info and notify callbacks."""
        self._map_info = map_info
        _LOGGER.debug("Map info updated: id=%s, name=%s, state=%s",
                     map_info.get('id'), map_info.get('name'), map_info.get('map_state'))
        for callback in list(self.map_callbacks):
            self._dispatch(callback, map_info)

    def _get_map_field(self, data: dict[str, Any], *keys: str) -> Any | None:
        """Get a value from among the possible field names."""
        for key in keys:
            if key in data:
                return data.get(key)
        return None

    def _build_map_info_from_map_data(self, map_data: dict[str, Any]) -> dict[str, Any] | None:
        """Build/complete map_info from the HTTP map data."""
        if not isinstance(map_data, dict):
            return None
        base = dict(self._map_info) if self._map_info else {}
        current_id = base.get("id")
        new_id = self._get_map_field(map_data, "id", "map_id", "mapId")
        if new_id is not None and new_id != current_id:
            base = {}
        mapped = {
            "id": new_id,
            "name": self._get_map_field(map_data, "name", "map_name", "mapName"),
            "map_state": self._get_map_field(map_data, "map_state", "mapState", "state"),
            "regions": map_data.get("regions"),
            "clean_info": self._get_map_field(map_data, "clean_info", "cleanInfo"),
            "total_area": self._get_map_field(map_data, "total_area", "totalArea"),
            "sub_regions": self._get_map_field(map_data, "sub_regions", "subRegions"),
        }
        for key, value in mapped.items():
            if value is not None:
                base[key] = value
        if not base:
            return None
        if "map_state" not in base:
            base["map_state"] = "unknown"
        return base

    def _get_meta_seq(self, meta: dict[str, Any], label: str, warn: bool = True) -> int:
        """Parse the seq from the meta."""
        try:
            return int(meta.get("seq", -1))
        except (ValueError, TypeError):
            if warn:
                _LOGGER.warning("Invalid %s meta seq: %s", label, meta.get("seq"))
            return -1

    def _should_replace_pending(self, pending_meta: dict[str, Any] | None, seq: int, label: str) -> bool:
        """Whether to replace the cached pending meta with the new meta."""
        if pending_meta is None:
            return True
        pending_seq = self._get_meta_seq(pending_meta, label, warn=False)
        if seq == -1:
            return pending_seq == -1
        if pending_seq == -1:
            return True
        return seq > pending_seq

    def _get_retry_delay(self, count: int) -> float:
        """Get the retry delay (in seconds)."""
        delays = [2.0, 5.0, 10.0, 30.0]
        if count < len(delays):
            return delays[count]
        return delays[-1]

    def _reset_meta_retry(self, channel: _MetaFetchChannel) -> None:
        """Clear a channel's fetch retry state."""
        channel.retry_meta = None
        channel.retry_count = 0
        if channel.retry_task and not channel.retry_task.done():
            channel.retry_task.cancel()
        channel.retry_task = None

    def _reset_pending_meta(self) -> None:
        """Clear the pending meta."""
        for channel in self._meta_channels:
            channel.pending_meta = None

    def _schedule_meta_retry(
        self, channel: _MetaFetchChannel, meta: dict[str, Any]
    ) -> None:
        """Schedule a fetch retry for a channel."""
        # Don't schedule a new retry once shutdown has started; an in-flight
        # retry that already woke and cleared its task handle could otherwise
        # spawn a fresh retry task against a torn-down entry (leaks work).
        if self._stop_event.is_set():
            return
        channel.retry_meta = meta
        if channel.retry_task and not channel.retry_task.done():
            return
        delay = self._get_retry_delay(channel.retry_count)
        channel.retry_count += 1
        channel.retry_task = self.hass.async_create_task(
            self._async_retry_meta(channel, delay)
        )

    async def _async_retry_meta(
        self, channel: _MetaFetchChannel, delay: float
    ) -> None:
        """Retry a channel's fetch after a delay."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        channel.retry_task = None
        meta = channel.retry_meta
        if meta:
            await self._async_handle_meta(channel, meta)

    def _handle_map_info(self, payload: str) -> None:
        """Handle map info message."""
        try:
            map_info = json.loads(payload)
            self._update_map_info(map_info)

        except json.JSONDecodeError:
            _LOGGER.error("Failed to parse map info JSON: %s", payload[:200])
        except Exception as e:
            _LOGGER.error("Error handling map info: %s", e)

    def _apply_map_data(self, data: dict[str, Any]) -> None:
        """Apply fetched map data: cache it and derive/notify map info."""
        self._map_data = data
        map_info = self._build_map_info_from_map_data(data)
        if map_info is not None:
            self._update_map_info(map_info)

    def _apply_path_data(self, data: dict[str, Any]) -> None:
        """Apply fetched path data: cache it and notify path callbacks."""
        self._path_data = data
        for callback in self.path_callbacks:
            self.hass.async_create_task(callback(data))

    def _apply_history_path_data(self, data: dict[str, Any]) -> None:
        """Apply fetched history path data: cache it and notify callbacks."""
        self._history_path_data = data
        for callback in self.history_path_callbacks:
            self.hass.async_create_task(callback(data))

    async def _async_handle_meta(
        self, channel: _MetaFetchChannel, meta: dict[str, Any]
    ) -> None:
        """Handle a channel's meta message and fetch its data via HTTP."""
        seq = self._get_meta_seq(meta, channel.label)

        # When a new session starts (map created/switched/restored, new mowing
        # run) the device republishes meta with a seq counted from 0 again.
        # Without this reset the new meta is dropped by the seq <= channel.seq
        # guard and the stale data stays visible (e.g. the camera keeps showing
        # the old map) until the integration is reloaded. Treat a backward seq
        # as a reset.
        if seq != -1 and channel.seq != -1 and seq < channel.seq:
            _LOGGER.info(
                "%s seq went backward (%d -> %d); treating as new session",
                channel.label.capitalize(), channel.seq, seq,
            )
            channel.seq = -1
            channel.etag = None
        if seq != -1 and seq <= channel.seq:
            return
        if seq != -1 and seq > channel.seq:
            self._reset_meta_retry(channel)
        if seq == -1:
            now = time.monotonic()
            if (now - channel.no_seq_last_fetch) < self._no_seq_min_interval:
                return
        if channel.fetching:
            if self._should_replace_pending(channel.pending_meta, seq, channel.label):
                channel.pending_meta = meta
            return

        channel.fetching = True
        try:
            data, etag, ok, _not_modified = await self._async_fetch_json(meta, channel.etag)
            if ok:
                if seq != -1:
                    channel.seq = seq
                else:
                    channel.no_seq_last_fetch = time.monotonic()
                self._reset_meta_retry(channel)
            if etag:
                channel.etag = etag
            if data is not None:
                channel.apply_data(data)
            if not ok:
                self._schedule_meta_retry(channel, meta)
        except Exception as e:
            _LOGGER.error("Failed to fetch %s data: %s", channel.label, e)
            self._schedule_meta_retry(channel, meta)
        finally:
            channel.fetching = False
            pending_meta = channel.pending_meta
            channel.pending_meta = None
            if pending_meta:
                pending_seq = self._get_meta_seq(pending_meta, channel.label, warn=False)
                if pending_seq == -1 or pending_seq > channel.seq:
                    self.hass.async_create_task(
                        self._async_handle_meta(channel, pending_meta)
                    )

    async def _async_fetch_json(
        self,
        meta: dict[str, Any],
        etag: str | None,
    ) -> tuple[dict[str, Any] | None, str | None, bool, bool]:
        """Fetch JSON data via HTTP using meta info."""
        http_port = meta.get("http_port")
        http_path = meta.get("http_path")
        token = meta.get("token")
        if not http_port or not http_path or not token:
            _LOGGER.warning("Incomplete meta for HTTP fetch: %s", meta)
            return None, etag, False, False

        url = f"http://{self.host}:{http_port}{http_path}"
        headers = {"Authorization": f"Bearer {token}"}
        if etag:
            headers["If-None-Match"] = etag

        session = async_get_clientsession(self.hass)
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 304:
                return None, etag, True, True
            if resp.status >= 400:
                _LOGGER.error("HTTP fetch failed: %s status=%d", url, resp.status)
                return None, etag, False, False
            new_etag = resp.headers.get("ETag") or etag
            raw = await resp.read()
            # Decompress (the protocol gzips large bodies) and parse in one
            # executor job so neither step blocks the event loop.
            data = await self.hass.async_add_executor_job(_decompress_and_parse, raw)
            return data, new_etag, True, False

    @staticmethod
    def _format_firmware_version(info: dict[str, Any]) -> str | None:
        """Build the firmware version string shown on the device page."""
        overall = info.get("overall")
        if overall is None:
            return None
        ha_version = info.get("module", {}).get("home_assistant")
        if ha_version is not None:
            return f"{overall}.{ha_version}"
        return str(overall)

    def _device_identifiers(self) -> set[tuple[str, str]]:
        """Return the device registry identifiers for this mower."""
        return {(DOMAIN, self.basic_data.device_uid or self.basic_data.host)}

    async def _async_adopt_serial(self, serial: str) -> None:
        """Adopt the device serial (dp_102 ``sn``) as the stable identity.

        Entries start keyed on the host/IP because the serial only becomes
        known after the first MQTT connect. Once it arrives, re-key the
        entity registry unique_ids, the device registry identifier and the
        config entry itself; the entry-update listener then reloads the
        entry so freshly created entities match the migrated registry.
        A DHCP address change can no longer orphan the registry afterwards.
        """
        entry_id = self.basic_data.entry_id
        if entry_id is None:
            return
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return
        if entry.state is ConfigEntryState.SETUP_IN_PROGRESS:
            # A retained dp_102 typically arrives while the platforms are
            # still being set up (the hub starts before they are forwarded).
            # Migrating mid-setup re-keys the registry under the feet of the
            # entities still being added, which splits the device in two.
            # Park the serial; async_setup_entry consumes it once loaded.
            self._pending_serial = serial
            return
        stored = entry.data.get(CONF_SERIAL)
        if stored == serial:
            # Keep the runtime identity in sync for repeat dp_102 pushes.
            self.basic_data.device_uid = serial
            return
        if stored is not None:
            _LOGGER.warning(
                "Device serial changed from %s to %s (different mower at the "
                "same address?); keeping the existing registry identity",
                stored, serial,
            )
            return

        _LOGGER.info("Adopting device serial as the stable device identity")
        old_uid = self.basic_data.device_uid or self.basic_data.host
        old_fragment = f"terramow@{old_uid}"
        new_fragment = f"terramow@{serial}"

        entity_registry = er.async_get(self.hass)
        for reg_entry in er.async_entries_for_config_entry(entity_registry, entry_id):
            if old_fragment in reg_entry.unique_id:
                entity_registry.async_update_entity(
                    reg_entry.entity_id,
                    new_unique_id=reg_entry.unique_id.replace(
                        old_fragment, new_fragment
                    ),
                )

        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get_device({(DOMAIN, old_uid)})
        if device_entry:
            device_registry.async_update_device(
                device_entry.id, new_identifiers={(DOMAIN, serial)}
            )

        # Updating the entry fires the registered update listener, which
        # reloads the entry; the reloaded entities then generate the
        # serial-based unique_ids that match the migrated registry entries.
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SERIAL: serial}, unique_id=serial
        )

    async def async_adopt_pending_serial(self) -> None:
        """Run a serial adoption that arrived during entry setup."""
        serial = self._pending_serial
        self._pending_serial = None
        if not serial:
            return
        entry_id = self.basic_data.entry_id
        if entry_id is not None:
            # Scheduled at the end of async_setup_entry; eager task start
            # would otherwise run this while setup is still finishing and
            # the adoption would just park the serial again. Yield until
            # the entry has actually left SETUP_IN_PROGRESS.
            for _ in range(10):
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if (
                    entry is None
                    or entry.state is not ConfigEntryState.SETUP_IN_PROGRESS
                ):
                    break
                await asyncio.sleep(0)
        await self._async_adopt_serial(serial)

    async def _async_update_device_sw_version(self, sw_version: str) -> None:
        """Asynchronously update the firmware version info in the device registry."""
        try:
            device_registry = dr.async_get(self.hass)
            device_entry = device_registry.async_get_device(
                self._device_identifiers()
            )
            if device_entry and device_entry.sw_version != sw_version:
                device_registry.async_update_device(
                    device_entry.id, sw_version=sw_version
                )
                _LOGGER.info("Device registry updated with firmware version: %s", sw_version)
        except Exception as e:
            _LOGGER.error("Error updating device firmware version: %s", e)

    async def _async_update_device_model(self, model_name: str) -> None:
        """Asynchronously update the model info in the device registry."""
        try:
            device_registry = dr.async_get(self.hass)

            # Look up the device and update its model info
            device_entry = device_registry.async_get_device(self._device_identifiers())
            if device_entry:
                device_registry.async_update_device(
                    device_entry.id,
                    model=model_name
                )
                _LOGGER.info("Device registry updated with new model: %s", model_name)
            else:
                _LOGGER.warning("Device not found in registry for update")
        except Exception as e:
            _LOGGER.error("Error updating device registry: %s", e)

    def _handle_model_name(self, payload: str) -> None:
        """Handle device model name message."""
        try:
            # The payload is directly the model name string
            model_name = payload.strip()
            if model_name:
                old_model = self.device_model
                self.device_model = model_name
                _LOGGER.info("Device model updated: %s -> %s", old_model, model_name)

                self._dispatch(self._async_update_device_model, model_name)

                # Notify entities to refresh (e.g. the model in device_info)
                self._notify_state_listeners()
            else:
                _LOGGER.warning("Received empty model name, keeping default")
        except Exception as e:
            _LOGGER.error("Error handling model name: %s", e)

    @property
    def map_info(self) -> dict[str, Any]:
        """Get current map info."""
        return self._map_info

    @property
    def map_data(self) -> dict[str, Any]:
        """Get HTTP-fetched map data."""
        return self._map_data

    @property
    def path_data(self) -> dict[str, Any]:
        """Get HTTP-fetched path data."""
        return self._path_data

    @property
    def history_path_data(self) -> dict[str, Any]:
        """Get HTTP-fetched history path data."""
        return self._history_path_data

    @property
    def pose(self) -> dict[str, Any]:
        """Get current pose data."""
        return self._pose

    @property
    def global_params(self) -> dict[str, Any]:
        """Get current global parameters from dp_155."""
        return self._global_params

    @property
    def map_status(self) -> dict[str, Any]:
        """Get current map status from dp_117."""
        return self._map_status

    @property
    def current_work_data(self) -> dict[str, Any]:
        """Get current work data from dp_113."""
        return self._current_work_data

    @property
    def statistics_data(self) -> dict[str, Any]:
        """Get statistics data from dp_124."""
        return self._statistics_data

    @property
    def base_station_time(self) -> dict[str, Any]:
        """Get base station time from dp_125."""
        return self._base_station_time

    @property
    def blade_time(self) -> dict[str, Any]:
        """Get blade time from dp_126."""
        return self._blade_time

    @property
    def schedule_data(self) -> dict[str, Any]:
        """Get schedule data from dp_138."""
        return self._schedule_data

    @property
    def battery_status(self) -> dict[str, Any]:
        """Get current battery status from dp_108."""
        return self._battery_status

    @property
    def battery_level(self) -> int | None:
        """Get the current battery percentage from dp_8."""
        return self._battery_level

    @property
    def firmware_version_name(self) -> str | None:
        """Get the real firmware version (dp_102 ``version``), e.g. '9.9.210'."""
        version = self._robot_info.get("version")
        return version if isinstance(version, str) and version else None

    @property
    def component_versions(self) -> dict[str, Any]:
        """Get the per-component firmware versions (dp_129)."""
        return self._component_versions

    @property
    def error_list(self) -> list[Any]:
        """Get the active-error list (dp_116, undocumented)."""
        return self._error_list

    @property
    def event_list(self) -> list[Any]:
        """Get the event log (dp_123, undocumented)."""
        return self._event_list

    @property
    def cellular_info(self) -> dict[str, Any]:
        """Get the cellular/4G modem info (dp_135, undocumented)."""
        return self._cellular_info

    @property
    def environment_info(self) -> dict[str, Any]:
        """Get the environment/status info (dp_152, undocumented)."""
        return self._environment_info

    @property
    def weather_info(self) -> dict[str, Any]:
        """Get the extreme-weather warning info (dp_157, undocumented)."""
        return self._weather_info

    @property
    def operating_modes(self) -> dict[str, Any]:
        """Get the operating-mode triple (dp_154, undocumented)."""
        return self._operating_modes

    @property
    def full_schedule(self) -> dict[str, Any]:
        """Get the full weekly schedule list (dp_122, undocumented)."""
        return self._full_schedule

    @property
    def state_flag_134(self) -> dict[str, Any]:
        """Get the undecoded binary flag payload (dp_134, undocumented)."""
        return self._state_flag_134

    @property
    def map_save_progress(self) -> dict[str, Any]:
        """Get the map-save / upload progress payload (dp_118, undocumented)."""
        return self._map_save_progress

    @property
    def advanced_settings(self) -> dict[str, Any]:
        """Get the advanced settings block (dp_150, undocumented)."""
        return self._advanced_settings

    @property
    def is_robot_navi_located(self) -> bool | None:
        """Get whether the robot is navigation-located (from dp_107)."""
        return self._is_robot_navi_located

    @property
    def is_upgrading(self) -> bool | None:
        """Get whether the robot is upgrading firmware (from dp_107)."""
        return self._is_upgrading

    @property
    def power_mode(self) -> str | None:
        """Get current power mode from dp_107."""
        return self._power_mode

    @property
    def task_status(self) -> dict[str, Any]:
        """Get current task status raw payload from dp_107."""
        return self._task_status

    @property
    def has_error(self) -> bool:
        """Return whether the robot currently reports a fault (dp_107)."""
        return bool(self._task_status.get("has_error", False))

    @property
    def back_to_station_reason(self) -> str | None:
        """Return the raw back_to_station_reason enum string from dp_107."""
        return self._task_status.get("back_to_station_reason")

    @property
    def is_saving_data(self) -> bool:
        """Return whether the robot is saving data (dp_107).

        While true the robot may not respond to operation commands.
        """
        return bool(self._task_status.get("is_saving_data", False))

    @property
    def is_data_conversion_in_progress(self) -> bool:
        """Return whether a data compatibility conversion is running (dp_107)."""
        return bool(self._task_status.get("is_data_conversion_in_progress", False))

    @property
    def compatibility_status(self) -> str:
        """Return current compatibility status."""
        return self.basic_data.compatibility_status

    @property
    def compatibility_message(self) -> str:
        """Return current compatibility message."""
        return self.basic_data.get_compatibility_message()

    @property
    def firmware_version_info(self) -> dict[str, Any]:
        """Return firmware version information."""
        return self.basic_data.firmware_version or {}

    def publish_data_point(self, dp_id: int, data: dict[str, Any]) -> None:
        """Publish a command/data payload to a device data point.

        Commands are sent at QoS 1 so a brief reconnect buffers them instead of
        dropping them. If the MQTT client is missing or disconnected, or the
        broker rejects the publish, raise ``HomeAssistantError`` so a service
        call surfaces the failure instead of silently reporting success — the
        mower would otherwise keep mowing while ``dock``/``pause`` "succeed".

        Only the synchronous command path (lawn_mower/button/select/number/
        switch service calls) lets this propagate; the one background caller,
        ``_request_compatibility_info`` on the MQTT worker thread, wraps this in
        its own ``try/except`` so a raised error never kills the worker.
        """
        topic = f"data_point/{dp_id}/app"
        _LOGGER.debug("Publishing data to topic %s: %s", topic, data)
        payload = json.dumps(data)
        client = self.mqtt_client
        if client is None or not client.is_connected():
            _LOGGER.error("Cannot publish to %s: MQTT client not connected", topic)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_not_delivered",
            )
        info = client.publish(topic, payload, qos=1)
        if info.rc != mqtt_client.MQTT_ERR_SUCCESS:
            _LOGGER.error("MQTT publish to %s failed with rc=%s", topic, info.rc)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_not_delivered",
            )

    def get_cmd_seq(self) -> int:
        """Generate a new command sequence number (thread-safe)."""
        with self._cmd_seq_lock:
            self.cmd_seq += 1
            return self.cmd_seq

    def start_mowing(self) -> None:
        """Start mowing, resuming a paused or station-waiting job."""
        self._ensure_command_allowed()

        if self.mission in MOW_MISSIONS:
            if self.sub_mission == SubMission.SUB_MISSION_FLEXIBLE_STATION_WAIT:
                _LOGGER.info("SubMissionWaitInStation resume mow")
                self._resume_mow()
            else:
                if self.mission_state == MissionState.MISSION_STATE_RUNNING:
                    _LOGGER.info("Now is mowing, can not start mow again")
                elif self.mission_state == MissionState.MISSION_STATE_PAUSE:
                    _LOGGER.info("Mission paused, resume mow")
                    self._resume_mow()
        else:
            _LOGGER.info("START CLEAN : Sending start command")
            self._start_normal_mow()

    def pause(self) -> None:
        """Pause the running job."""
        self._ensure_command_allowed()

        if self.mission in MOW_MISSIONS:
            if self.sub_mission == SubMission.SUB_MISSION_FLEXIBLE_STATION_WAIT:
                _LOGGER.info("SubMissionWaitInStation, now is not ok to pause mow")
            else:
                if self.mission_state == MissionState.MISSION_STATE_RUNNING:
                    _LOGGER.info("PAUSE CLEAN : Sending pause command")
                    self._send_pause_command()
                elif self.mission_state == MissionState.MISSION_STATE_PAUSE:
                    _LOGGER.info("Now is paused, can not pause mow again")
        else:
            if self.mission_state == MissionState.MISSION_STATE_RUNNING:
                _LOGGER.info("PAUSE CLEAN : Sending pause command")
                self._send_pause_command()
            elif self.mission_state == MissionState.MISSION_STATE_PAUSE:
                _LOGGER.info("Now is paused, can not pause mow again")

    def dock(self) -> None:
        """Send the mower back to the base station."""
        self._ensure_command_allowed()

        if self.mission in RECHARGE_MISSIONS:
            if self.mission_state == MissionState.MISSION_STATE_RUNNING:
                _LOGGER.info("Now is not ok to start recharge")
            elif self.mission_state == MissionState.MISSION_STATE_PAUSE:
                _LOGGER.info("ResumeRecharge : Resuming recharge")
                self._resume_recharge()
        else:
            _LOGGER.info("StartRecharge : Sending recharge command")
            self._start_normal_recharge()

    def _start_normal_mow(self) -> None:
        """Start normal mowing"""
        command = {
            'seq': self.get_cmd_seq(),
            'mode': 'START_MODE_GLOBAL_CLEAN',
            'global_clean': {'restart': False}
        }
        self.publish_data_point(103, command)

    def _build_select_region_command(self, region_ids: list[int]) -> dict[str, Any]:
        """Build the dp_103 selective-mow command payload."""
        return {
            'seq': self.get_cmd_seq(),
            'mode': 'START_MODE_SELECT_REGION_CLEAN',
            'select_region': {'region_id': list(region_ids)}
        }

    def start_select_region_clean(self, region_ids: list[int]) -> None:
        """Start mowing for the specified sub-region IDs (fire-and-forget)."""
        if not region_ids:
            _LOGGER.warning("start_select_region_clean called with empty region_ids")
            return
        self._ensure_command_allowed()
        _LOGGER.info("START SELECT REGION CLEAN: regions=%s", region_ids)
        self.publish_data_point(103, self._build_select_region_command(region_ids))

    async def async_start_select_region_clean(self, region_ids: list[int]) -> None:
        """Start a selective mow and wait for the device's dp_119 ack.

        The confirmed variant of :meth:`start_select_region_clean`, used by
        the ``terramow.start_select_region`` service (and through it the map
        card's tap-to-mow flow) so a rejection reaches the caller instead of
        silently succeeding.
        """
        if not region_ids:
            _LOGGER.warning("start_select_region_clean called with empty region_ids")
            return
        self._ensure_command_allowed()
        _LOGGER.info("START SELECT REGION CLEAN (confirmed): regions=%s", region_ids)
        await self.async_publish_with_ack(
            103, self._build_select_region_command(region_ids)
        )

    def _start_edge_trim(self) -> None:
        """Start edge-trim mowing"""
        command = {
            'seq': self.get_cmd_seq(),
            'mode': 'START_MODE_EDGE_TRIM_CLEAN'
        }
        self.publish_data_point(103, command)

    def start_edge_trim(self) -> None:
        """Public wrapper to start edge-trim mowing."""
        self._ensure_command_allowed()

        _LOGGER.info("START EDGE TRIM : Sending edge trim command")
        self._start_edge_trim()

    def _resume_mow(self) -> None:
        """Resume mowing"""
        command = {'seq': self.get_cmd_seq()}
        self.publish_data_point(106, command)

    def _send_pause_command(self) -> None:
        """Send pause command"""
        command = {'seq': self.get_cmd_seq()}
        self.publish_data_point(105, command)

    def _start_normal_recharge(self) -> None:
        """Start normal recharging"""
        command = {
            'seq': self.get_cmd_seq(),
            'mode': 'START_MODE_RETURN'
        }
        self.publish_data_point(103, command)

    def _resume_recharge(self) -> None:
        """Resume recharging"""
        # Resuming recharge is equivalent to resuming mowing
        return self._resume_mow()

    def _request_compatibility_info(self) -> None:
        """Request version compatibility information."""
        try:
            _LOGGER.info("Requesting version compatibility information")
            # Send an empty request to obtain the compatibility information
            request_data = {"seq": self.get_cmd_seq()}
            self.publish_data_point(COMPATIBILITY_INFO_DP, request_data)
        except Exception as e:
            _LOGGER.error("Failed to request version compatibility information: %s", e)

    def _request_full_schedule(self) -> None:
        """Request the full weekly schedule (dp_122 GET).

        Mirrors ``_request_compatibility_info``: a read-only query the device
        answers with its schedule list. Wrapped so a failure never kills the
        MQTT worker thread.
        """
        try:
            _LOGGER.info("Requesting full weekly schedule")
            request_data = {"cmd_type": "SCHEDULE_CMD_TYPE_GET", "seq": self.get_cmd_seq()}
            self.publish_data_point(122, request_data)
        except Exception as e:
            _LOGGER.error("Failed to request full weekly schedule: %s", e)
