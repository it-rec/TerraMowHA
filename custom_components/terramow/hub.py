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
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

import aiohttp
import paho.mqtt.client as mqtt_client
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    COMPATIBILITY_INFO_DP,
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

if TYPE_CHECKING:
    from . import TerraMowBasicData

_LOGGER = logging.getLogger(__name__)

# Define the regular expression pattern
TOPIC_PATTERN = re.compile(r"^data_point/(\d+)/robot$")


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
        self._map_info: dict[str, Any] = {}  # Stores the current map info
        self._map_meta: dict[str, Any] = {}  # Stores map meta info
        self._path_meta: dict[str, Any] = {}  # Stores path meta info
        self._history_path_meta: dict[str, Any] = {}  # Stores history path meta info
        self._map_data: dict[str, Any] = {}  # Stores map data fetched over HTTP
        self._path_data: dict[str, Any] = {}  # Stores path data fetched over HTTP
        self._history_path_data: dict[str, Any] = {}  # Stores history path data fetched over HTTP
        self._pose: dict[str, Any] = {}  # Stores the real-time pose
        self._pending_map_meta: dict[str, Any] | None = None
        self._pending_path_meta: dict[str, Any] | None = None
        self._pending_history_path_meta: dict[str, Any] | None = None
        self._map_retry_meta: dict[str, Any] | None = None
        self._path_retry_meta: dict[str, Any] | None = None
        self._history_path_retry_meta: dict[str, Any] | None = None
        self._map_retry_count = 0
        self._path_retry_count = 0
        self._history_path_retry_count = 0
        self._map_retry_task: asyncio.Task[Any] | None = None
        self._path_retry_task: asyncio.Task[Any] | None = None
        self._history_path_retry_task: asyncio.Task[Any] | None = None
        self._map_no_seq_last_fetch = 0.0
        self._path_no_seq_last_fetch = 0.0
        self._history_path_no_seq_last_fetch = 0.0
        self._no_seq_min_interval = 5.0
        self._map_seq = -1
        self._path_seq = -1
        self._history_path_seq = -1
        self._map_etag: str | None = None
        self._path_etag: str | None = None
        self._history_path_etag: str | None = None
        self._fetching_map = False
        self._fetching_path = False
        self._fetching_history_path = False
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
        self._task_status: dict[str, Any] = {}  # Store dp_107 task status raw payload
        self._seen_unknown_dp_ids: set[int] = set()  # Unknown data points already logged
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

        self.cmd_seq = random.randint(0, 0xFFFFFFFF)  # Generate a random command sequence number
        # get_cmd_seq is reachable from the paho network thread (compatibility
        # request on connect) and from executor threads (sync command senders),
        # so the increment must be atomic to avoid handing out a duplicate seq.
        self._cmd_seq_lock = threading.Lock()

        self._last_control_time = time.monotonic()
        self._control_interval = 1.0  # Control interval time

        _LOGGER.debug("TerraMowHub created with host %s", self.host)

    @property
    def device_model(self) -> str:
        """Return the device model."""
        return self._device_model

    @device_model.setter
    def device_model(self, model_name: str) -> None:
        """Update the device model."""
        self._device_model = model_name

    def register_state_listener(self, listener: Callable[[], None]) -> None:
        """Register a listener called on connection/dp_107/model changes.

        Listeners may be invoked from the MQTT worker thread, so they must
        be thread-safe (e.g. use ``schedule_update_ha_state``).
        """
        self._state_listeners.append(listener)

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
        _LOGGER.debug("MQTT connection params: username=%s, password=%s", MQTT_USERNAME, self.password)

        self.mqtt_client = mqtt_client.Client()
        self.mqtt_client.username_pw_set(MQTT_USERNAME, self.password)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message

        # Start MQTT loop thread
        _LOGGER.debug("Starting MQTT thread")
        self.mqtt_thread = threading.Thread(target=self.mqtt_loop)
        self.mqtt_thread.daemon = True
        self.mqtt_thread.start()

        self.register_all_callbacks()
        _LOGGER.debug("MQTT client startup completed")

    async def async_stop(self) -> None:
        """Stop the MQTT client and clean up resources."""
        _LOGGER.info("Stopping MQTT client")
        self._stop_event.set()
        self._reset_map_retry()
        self._reset_path_retry()
        self._reset_history_path_retry()
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
        self.register_callback(150, self.on_advanced_settings)
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
        plus serial/network identifiers. Only the version is surfaced to Home
        Assistant; the identifiers are kept private.
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
                self.hass.add_job(self._async_update_device_sw_version, version)

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
                    data[key] = None

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
                self.hass.add_job(self._async_update_device_sw_version, sw_version)

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
            # Subscribe to topics
            for dp_id in range(201):
                topic = f"data_point/{dp_id}/robot"
                client.subscribe(topic)
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
            _LOGGER.info("Subscribed to %s topic", MODEL_NAME_TOPIC)

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
        payload = msg.payload.decode()

        if topic != POSE_TOPIC:
            _LOGGER.debug("Received MQTT message: topic=%s, payload=%s", topic, payload)

        # Handle map meta info
        if topic == MAP_META_TOPIC:
            try:
                meta = json.loads(payload)
                self._map_meta = meta
                self.hass.add_job(self._async_handle_map_meta, meta)
            except json.JSONDecodeError:
                _LOGGER.error("Failed to parse map meta JSON: %s", payload[:200])
            except Exception as e:
                _LOGGER.error("Error handling map meta: %s", e)
            return

        # Handle path meta info
        if topic == PATH_META_TOPIC:
            try:
                meta = json.loads(payload)
                self._path_meta = meta
                self.hass.add_job(self._async_handle_path_meta, meta)
            except json.JSONDecodeError:
                _LOGGER.error("Failed to parse path meta JSON: %s", payload[:200])
            except Exception as e:
                _LOGGER.error("Error handling path meta: %s", e)
            return

        # Handle history path meta info
        if topic == PATH_HISTORY_META_TOPIC:
            try:
                meta = json.loads(payload)
                self._history_path_meta = meta
                self.hass.add_job(self._async_handle_history_path_meta, meta)
            except json.JSONDecodeError:
                _LOGGER.error("Failed to parse history path meta JSON: %s", payload[:200])
            except Exception as e:
                _LOGGER.error("Error handling history path meta: %s", e)
            return

        # Handle the real-time pose
        if topic == POSE_TOPIC:
            try:
                pose = json.loads(payload)
                self._pose = pose
                for callback in self.pose_callbacks:
                    self.hass.add_job(callback, pose)
            except json.JSONDecodeError:
                _LOGGER.error("Failed to parse pose JSON: %s", payload[:200])
            except Exception as e:
                _LOGGER.error("Error handling pose: %s", e)
            return

        # Handle the map info topic
        if topic == MAP_INFO_TOPIC:
            _LOGGER.debug("Received map info message, size: %d bytes", len(payload))
            self._handle_map_info(payload)
            return

        # Handle the device model topic
        if topic == MODEL_NAME_TOPIC:
            _LOGGER.info("Received device model message: %s", payload)
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
            for callback in callbacks:
                self.hass.add_job(callback, payload)
        else:
            # Help discover undocumented data points (e.g. lift alarms, schedule
            # switches, error codes): each unknown dp_id is logged once at INFO,
            # while the full payload is continuously logged at DEBUG. The latest
            # payload is also kept for the diagnostics export so undocumented
            # dps can be identified from real data without live log capture.
            self._unknown_dp_payloads[dp_id] = payload[:500]
            if dp_id not in self._seen_unknown_dp_ids:
                self._seen_unknown_dp_ids.add(dp_id)
                _LOGGER.info(
                    "Received undocumented data point %d (no handler registered). "
                    "First payload: %s. Enable debug logging for the terramow "
                    "integration to record all payloads for this data point.",
                    dp_id, payload[:500],
                )
            else:
                _LOGGER.debug("Unhandled data point %d payload: %s", dp_id, payload[:2000])

    def register_callback(self, dp_id: int, callback: Callable[..., Any]) -> None:
        """Register a callback function for a specific dp_id."""
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        if dp_id not in self.callbacks:
            self.callbacks[dp_id] = []
        self.callbacks[dp_id].append(callback)
        _LOGGER.debug(f"Callback registered for dp_id: {dp_id}")

    def register_map_callback(self, callback: Callable[..., Any]) -> None:
        """Register a callback function for map info updates."""
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.map_callbacks.append(callback)
        _LOGGER.debug("Map callback registered")
        # If map data already exists, trigger the callback immediately
        if self._map_info:
            self.hass.add_job(callback, self._map_info)

    def register_pose_callback(self, callback: Callable[..., Any]) -> None:
        """Register a callback function for pose updates."""
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.pose_callbacks.append(callback)
        _LOGGER.debug("Pose callback registered")
        if self._pose:
            self.hass.add_job(callback, self._pose)

    def register_path_callback(self, callback: Callable[..., Any]) -> None:
        """Register a callback function for path data updates."""
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.path_callbacks.append(callback)
        _LOGGER.debug("Path callback registered")
        if self._path_data:
            self.hass.add_job(callback, self._path_data)

    def register_history_path_callback(self, callback: Callable[..., Any]) -> None:
        """Register a callback function for history path data updates."""
        if not callable(callback):
            raise ValueError("Callback must be a callable function.")
        self.history_path_callbacks.append(callback)
        _LOGGER.debug("History path callback registered")
        if self._history_path_data:
            self.hass.add_job(callback, self._history_path_data)

    def _update_map_info(self, map_info: dict[str, Any]) -> None:
        """Update map info and notify callbacks."""
        self._map_info = map_info
        _LOGGER.debug("Map info updated: id=%s, name=%s, state=%s",
                     map_info.get('id'), map_info.get('name'), map_info.get('map_state'))
        for callback in self.map_callbacks:
            self.hass.add_job(callback, map_info)

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

    def _reset_map_retry(self) -> None:
        """Clear the map fetch retry state."""
        self._map_retry_meta = None
        self._map_retry_count = 0
        if self._map_retry_task and not self._map_retry_task.done():
            self._map_retry_task.cancel()
        self._map_retry_task = None

    def _reset_path_retry(self) -> None:
        """Clear the path fetch retry state."""
        self._path_retry_meta = None
        self._path_retry_count = 0
        if self._path_retry_task and not self._path_retry_task.done():
            self._path_retry_task.cancel()
        self._path_retry_task = None

    def _reset_history_path_retry(self) -> None:
        """Clear the history path fetch retry state."""
        self._history_path_retry_meta = None
        self._history_path_retry_count = 0
        if self._history_path_retry_task and not self._history_path_retry_task.done():
            self._history_path_retry_task.cancel()
        self._history_path_retry_task = None

    def _reset_pending_meta(self) -> None:
        """Clear the pending meta."""
        self._pending_map_meta = None
        self._pending_path_meta = None
        self._pending_history_path_meta = None

    def _schedule_map_retry(self, meta: dict[str, Any]) -> None:
        """Schedule a map fetch retry."""
        # Don't schedule a new retry once shutdown has started; an in-flight
        # retry that already woke and cleared its task handle could otherwise
        # spawn a fresh retry task against a torn-down entry (leaks work).
        if self._stop_event.is_set():
            return
        self._map_retry_meta = meta
        if self._map_retry_task and not self._map_retry_task.done():
            return
        delay = self._get_retry_delay(self._map_retry_count)
        self._map_retry_count += 1
        self._map_retry_task = self.hass.async_create_task(self._async_retry_map(delay))

    def _schedule_path_retry(self, meta: dict[str, Any]) -> None:
        """Schedule a path fetch retry."""
        if self._stop_event.is_set():
            return
        self._path_retry_meta = meta
        if self._path_retry_task and not self._path_retry_task.done():
            return
        delay = self._get_retry_delay(self._path_retry_count)
        self._path_retry_count += 1
        self._path_retry_task = self.hass.async_create_task(self._async_retry_path(delay))

    def _schedule_history_path_retry(self, meta: dict[str, Any]) -> None:
        """Schedule a history path fetch retry."""
        if self._stop_event.is_set():
            return
        self._history_path_retry_meta = meta
        if self._history_path_retry_task and not self._history_path_retry_task.done():
            return
        delay = self._get_retry_delay(self._history_path_retry_count)
        self._history_path_retry_count += 1
        self._history_path_retry_task = self.hass.async_create_task(
            self._async_retry_history_path(delay)
        )

    async def _async_retry_map(self, delay: float) -> None:
        """Retry the map fetch after a delay."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._map_retry_task = None
        meta = self._map_retry_meta
        if meta:
            await self._async_handle_map_meta(meta)

    async def _async_retry_path(self, delay: float) -> None:
        """Retry the path fetch after a delay."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._path_retry_task = None
        meta = self._path_retry_meta
        if meta:
            await self._async_handle_path_meta(meta)

    async def _async_retry_history_path(self, delay: float) -> None:
        """Retry the history path fetch after a delay."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._history_path_retry_task = None
        meta = self._history_path_retry_meta
        if meta:
            await self._async_handle_history_path_meta(meta)

    def _handle_map_info(self, payload: str) -> None:
        """Handle map info message."""
        try:
            map_info = json.loads(payload)
            self._update_map_info(map_info)

        except json.JSONDecodeError:
            _LOGGER.error("Failed to parse map info JSON: %s", payload[:200])
        except Exception as e:
            _LOGGER.error("Error handling map info: %s", e)

    async def _async_handle_map_meta(self, meta: dict[str, Any]) -> None:
        """Handle map meta message and fetch map data via HTTP."""
        seq = self._get_meta_seq(meta, "map")

        # Same session-reset handling as the path/history meta handlers: when a
        # new map is created/switched/restored the device republishes meta with
        # a seq counted from 0 again. Without this reset the new meta is dropped
        # by the seq <= _map_seq guard and the camera keeps showing the old map
        # until the integration is reloaded. Treat a backward seq as a reset.
        if seq != -1 and self._map_seq != -1 and seq < self._map_seq:
            _LOGGER.info(
                "Map seq went backward (%d -> %d); treating as new session",
                self._map_seq, seq,
            )
            self._map_seq = -1
            self._map_etag = None
        if seq != -1 and seq <= self._map_seq:
            return
        if seq != -1 and seq > self._map_seq:
            self._reset_map_retry()
        if seq == -1:
            now = time.monotonic()
            if (now - self._map_no_seq_last_fetch) < self._no_seq_min_interval:
                return
        if self._fetching_map:
            if self._should_replace_pending(self._pending_map_meta, seq, "map"):
                self._pending_map_meta = meta
            return

        self._fetching_map = True
        try:
            data, etag, ok, _not_modified = await self._async_fetch_json(meta, self._map_etag)
            if ok:
                if seq != -1:
                    self._map_seq = seq
                else:
                    self._map_no_seq_last_fetch = time.monotonic()
                self._reset_map_retry()
            if etag:
                self._map_etag = etag
            if data is not None:
                self._map_data = data
                map_info = self._build_map_info_from_map_data(data)
                if map_info is not None:
                    self._update_map_info(map_info)
            if not ok:
                self._schedule_map_retry(meta)
        except Exception as e:
            _LOGGER.error("Failed to fetch map data: %s", e)
            self._schedule_map_retry(meta)
        finally:
            self._fetching_map = False
            pending_meta = self._pending_map_meta
            self._pending_map_meta = None
            if pending_meta:
                pending_seq = self._get_meta_seq(pending_meta, "map", warn=False)
                if pending_seq == -1 or pending_seq > self._map_seq:
                    self.hass.async_create_task(self._async_handle_map_meta(pending_meta))

    async def _async_handle_path_meta(self, meta: dict[str, Any]) -> None:
        """Handle path meta message and fetch path data via HTTP."""
        seq = self._get_meta_seq(meta, "path")

        # When a new mowing session starts, the device republishes path meta
        # with seq counted from 0 again. Without this reset, the new meta is
        # discarded by the seq <= _path_seq guard and the path stays hidden
        # until the integration is reloaded. Treat a backward seq as a reset.
        if seq != -1 and self._path_seq != -1 and seq < self._path_seq:
            _LOGGER.info(
                "Path seq went backward (%d -> %d); treating as new session",
                self._path_seq, seq,
            )
            self._path_seq = -1
            self._path_etag = None
        if seq != -1 and seq <= self._path_seq:
            return
        if seq != -1 and seq > self._path_seq:
            self._reset_path_retry()
        if seq == -1:
            now = time.monotonic()
            if (now - self._path_no_seq_last_fetch) < self._no_seq_min_interval:
                return
        if self._fetching_path:
            if self._should_replace_pending(self._pending_path_meta, seq, "path"):
                self._pending_path_meta = meta
            return

        self._fetching_path = True
        try:
            data, etag, ok, _not_modified = await self._async_fetch_json(meta, self._path_etag)
            if ok:
                if seq != -1:
                    self._path_seq = seq
                else:
                    self._path_no_seq_last_fetch = time.monotonic()
                self._reset_path_retry()
            if etag:
                self._path_etag = etag
            if data is not None:
                self._path_data = data
                for callback in self.path_callbacks:
                    self.hass.async_create_task(callback(data))
            if not ok:
                self._schedule_path_retry(meta)
        except Exception as e:
            _LOGGER.error("Failed to fetch path data: %s", e)
            self._schedule_path_retry(meta)
        finally:
            self._fetching_path = False
            pending_meta = self._pending_path_meta
            self._pending_path_meta = None
            if pending_meta:
                pending_seq = self._get_meta_seq(pending_meta, "path", warn=False)
                if pending_seq == -1 or pending_seq > self._path_seq:
                    self.hass.async_create_task(self._async_handle_path_meta(pending_meta))

    async def _async_handle_history_path_meta(self, meta: dict[str, Any]) -> None:
        """Handle history path meta message and fetch history path data via HTTP."""
        seq = self._get_meta_seq(meta, "history path")

        # Same session-reset handling as _async_handle_path_meta: a new mowing
        # session republishes meta with a seq starting from 0, which would
        # otherwise be dropped by the seq guard.
        if seq != -1 and self._history_path_seq != -1 and seq < self._history_path_seq:
            _LOGGER.info(
                "History path seq went backward (%d -> %d); treating as new session",
                self._history_path_seq, seq,
            )
            self._history_path_seq = -1
            self._history_path_etag = None
        if seq != -1 and seq <= self._history_path_seq:
            return
        if seq != -1 and seq > self._history_path_seq:
            self._reset_history_path_retry()
        if seq == -1:
            now = time.monotonic()
            if (now - self._history_path_no_seq_last_fetch) < self._no_seq_min_interval:
                return
        if self._fetching_history_path:
            if self._should_replace_pending(self._pending_history_path_meta, seq, "history path"):
                self._pending_history_path_meta = meta
            return

        self._fetching_history_path = True
        try:
            data, etag, ok, _not_modified = await self._async_fetch_json(meta, self._history_path_etag)
            if ok:
                if seq != -1:
                    self._history_path_seq = seq
                else:
                    self._history_path_no_seq_last_fetch = time.monotonic()
                self._reset_history_path_retry()
            if etag:
                self._history_path_etag = etag
            if data is not None:
                self._history_path_data = data
                for callback in self.history_path_callbacks:
                    self.hass.async_create_task(callback(data))
            if not ok:
                self._schedule_history_path_retry(meta)
        except Exception as e:
            _LOGGER.error("Failed to fetch history path data: %s", e)
            self._schedule_history_path_retry(meta)
        finally:
            self._fetching_history_path = False
            pending_meta = self._pending_history_path_meta
            self._pending_history_path_meta = None
            if pending_meta:
                pending_seq = self._get_meta_seq(pending_meta, "history path", warn=False)
                if pending_seq == -1 or pending_seq > self._history_path_seq:
                    self.hass.async_create_task(self._async_handle_history_path_meta(pending_meta))

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
            # Handle gzip compression manually: the protocol requires Content-Encoding: gzip
            if raw[:2] == b'\x1f\x8b':
                raw = await self.hass.async_add_executor_job(gzip.decompress, raw)
            text = raw.decode("utf-8")
            data = json.loads(text)
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

    async def _async_update_device_sw_version(self, sw_version: str) -> None:
        """Asynchronously update the firmware version info in the device registry."""
        try:
            device_registry = dr.async_get(self.hass)
            device_entry = device_registry.async_get_device(
                {('TerraMowLawnMower', self.basic_data.host)}
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
            device_identifier = ('TerraMowLawnMower', self.basic_data.host)

            # Look up the device and update its model info
            device_entry = device_registry.async_get_device({device_identifier})
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

                # Use hass.add_job to schedule the async device registry update onto the main event loop
                self.hass.add_job(self._async_update_device_model, model_name)

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
        _LOGGER.info("Publishing data to topic %s: %s", topic, data)
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

    def start_select_region_clean(self, region_ids: list[int]) -> None:
        """Start mowing for the specified sub-region IDs."""
        if not region_ids:
            _LOGGER.warning("start_select_region_clean called with empty region_ids")
            return
        self._ensure_command_allowed()
        command = {
            'seq': self.get_cmd_seq(),
            'mode': 'START_MODE_SELECT_REGION_CLEAN',
            'select_region': {'region_id': list(region_ids)}
        }
        _LOGGER.info("START SELECT REGION CLEAN: regions=%s", region_ids)
        self.publish_data_point(103, command)

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
