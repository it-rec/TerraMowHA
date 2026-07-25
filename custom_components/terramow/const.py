"""Constants for the TerraMow integration."""

from __future__ import annotations

from typing import overload

DOMAIN = "terramow"


@overload
def to_ha_enum_state(value: str) -> str: ...
@overload
def to_ha_enum_state(value: None) -> None: ...
def to_ha_enum_state(value: str | None) -> str | None:
    """Convert a device enum string to a Home Assistant state/option token.

    Device protocol enums are UPPERCASE (e.g. ``"MISSION_IDLE"``). Home Assistant
    requires entity state/option tokens (and their translation keys) to match
    ``[a-z0-9-_]+``. Device-facing code keeps the original UPPERCASE values; this
    helper is applied only at the entity surface (native_value / options).

    Callers always pass non-empty enum constants; the empty-string degenerate
    input still yields ``None`` at runtime.
    """
    return value.lower() if isinstance(value, str) and value else None


@overload
def to_device_enum(value: str) -> str: ...
@overload
def to_device_enum(value: None) -> None: ...
def to_device_enum(value: str | None) -> str | None:
    """Convert a Home Assistant enum option back to the device UPPERCASE form.

    The inverse of :func:`to_ha_enum_state`, used when a select option chosen in
    Home Assistant must be sent back to the device as its original enum string.
    """
    return value.upper() if isinstance(value, str) and value else None

MQTT_PORT = 1883

MQTT_USERNAME = "terramow"

# MQTT reconnect backoff (seconds)
# Base wait time after the first connection failure; subsequent retries back off
# exponentially, capped at MQTT_RECONNECT_MAX_DELAY.
# This way, when the mower is unreachable (asleep / returning to base / IP change)
# we don't spam an ERROR every few seconds or hammer the network.
MQTT_RECONNECT_BASE_DELAY = 5
MQTT_RECONNECT_MAX_DELAY = 60

# MQTT topics
MAP_INFO_TOPIC = "map/current/info"
MAP_META_TOPIC = "map/current/meta"
PATH_META_TOPIC = "path/current/meta"
PATH_HISTORY_META_TOPIC = "path/history/meta"
POSE_TOPIC = "pose/current"
MODEL_NAME_TOPIC = "model/name"

# Version compatibility constants
# Firmware home_assistant compatibility version required by the current plugin
CURRENT_HA_VERSION = 3

# Minimum firmware home_assistant compatibility version supported by the plugin.
# Version 2 lacks real-time map/path capabilities (which need version 3), but all
# other features work fully; some models (such as the S800) still report version 2
# on their latest firmware and should not be prompted to "upgrade firmware".
MIN_SUPPORTED_HA_VERSION = 2

# Minimum required firmware overall version number
MIN_REQUIRED_OVERALL_VERSION = 25

# Version compatibility check results
class CompatibilityStatus:
    COMPATIBLE = "compatible"
    UPGRADE_REQUIRED = "upgrade_required"  # firmware upgrade required
    DOWNGRADE_RECOMMENDED = "downgrade_recommended"  # plugin downgrade recommended
    INCOMPATIBLE = "incompatible"  # completely incompatible

# Data point ID used to obtain version compatibility information
COMPATIBILITY_INFO_DP = 127

# dp_119: generic per-command acknowledgement channel. The device echoes a
# command's seq with code 0 (OK) or a non-zero error code.
COMMAND_ACK_DP = 119

# How long a confirmed command waits for its dp_119 ack before falling back
# to optimistic (fire-and-forget) semantics. Field finding (V1000 fw28): the
# device does NOT ack commands sent by this integration at all — dp_119 acks
# observed there carry epoch-like seqs belonging to the mower's internal
# (BLE/cloud) commander. The wait is therefore short; a missing ack is never
# treated as a failure.
COMMAND_ACK_TIMEOUT = 2.0

# dp_122: full weekly schedule channel (GET/ADD/DELETE commands).
SCHEDULE_DP = 122

# Service weekday tokens -> device protocol enum values (dp_122 week_days).
WEEKDAY_TO_DEVICE = {
    "monday": "WEEK_DAY_MONDAY",
    "tuesday": "WEEK_DAY_TUESDAY",
    "wednesday": "WEEK_DAY_WEDNESDAY",
    "thursday": "WEEK_DAY_THURSDAY",
    "friday": "WEEK_DAY_FRIDAY",
    "saturday": "WEEK_DAY_SATURDAY",
    "sunday": "WEEK_DAY_SUNDAY",
}

# App-direction data-point topics. The vendor app writes commands here
# (schedule changes, settings, ...); the hub captures this traffic so
# undocumented write formats — e.g. the dp_122 schedule ADD/DELETE — can be
# documented from real app usage. Wildcard on purpose: the schedule write
# channel is not confirmed to be dp_122, and the app may use others.
APP_DP_TOPIC_FILTER = "data_point/+/app"

# Maintenance cycle constants (unit: minutes)
# Recommended blade cleaning cycle: 240 hours = 240 * 60 = 14400 minutes
BLADE_MAINTENANCE_CYCLE_MINUTES = 14400

# Recommended base station cleaning cycle: 30 days = 30 * 24 * 60 = 43200 minutes
BASE_STATION_MAINTENANCE_CYCLE_MINUTES = 43200

# dp_155 mowing speed enum (aligned with work_param.proto)
MOW_SPEED_TYPE_LOW = "MOW_SPEED_TYPE_LOW"
MOW_SPEED_TYPE_MEDIUM = "MOW_SPEED_TYPE_MEDIUM"
MOW_SPEED_TYPE_ADAPTIVE_HIGH = "MOW_SPEED_TYPE_ADAPTIVE_HIGH"
MOW_SPEED_TYPE_AUTO = "MOW_SPEED_TYPE_AUTO"

MOW_SPEED_TYPES = [
    MOW_SPEED_TYPE_LOW,
    MOW_SPEED_TYPE_MEDIUM,
    MOW_SPEED_TYPE_ADAPTIVE_HIGH,
    MOW_SPEED_TYPE_AUTO,
]

# Feature-level compatibility version: minimum version number where the mowing
# speed supports the AUTO setting
MIN_MOW_SPEED_VERSION_FOR_AUTO = 3

# dp_155 blade disk speed default value (matches the firmware's actual init path)
DEFAULT_BLADE_DISK_SPEED_TYPE = "BLADE_DISK_SPEED_TYPE_MEDIUM"

# Map camera output resolution (side length, square canvas)
# Config entry key for the mower's serial number (dp_102 "sn"), adopted on
# first connect as the stable device identity.
CONF_SERIAL = "serial"

CONF_MAP_RESOLUTION = "map_resolution"
DEFAULT_MAP_RESOLUTION = 1024
MAP_RESOLUTION_OPTIONS = [1024, 1536, 2048, 3072, 4096]

# Map camera color theme
CONF_MAP_THEME = "map_theme"
DEFAULT_MAP_THEME = "light"
MAP_THEME_OPTIONS = ["light", "dark"]

# Map camera coverage layer: shade the mowed swath at the real cutting width
CONF_MAP_SHOW_COVERAGE = "map_show_coverage"
DEFAULT_MAP_SHOW_COVERAGE = False

# Some firmware ends a finished job without emitting MISSION_STATE_COMPLETE, so
# the session progress never snaps to 100 % even when the lawn is done (it reads
# as "aborted"). With this on, any finished job is treated as complete (100 %),
# matching the vendor app; default off keeps the honest, counter-truthful value.
CONF_ASSUME_JOB_COMPLETE = "assume_job_complete"
DEFAULT_ASSUME_JOB_COMPLETE = False

# Real-world anchor for the device_tracker entity. The mower reports its pose
# only in map coordinates (millimetres, screen-style frame with +Y pointing
# down); pinning the base station's real latitude/longitude plus the compass
# bearing the top of the map points to turns those into GPS coordinates.
# All three are optional — without them no device_tracker is created.
CONF_GPS_LATITUDE = "gps_latitude"
CONF_GPS_LONGITUDE = "gps_longitude"
CONF_GPS_HEADING = "gps_heading"
DEFAULT_GPS_HEADING = 0.0

# The pose arrives at ~2 Hz. Writing a device_tracker state that often would
# flood the recorder for no benefit, so a new position is published only once
# the mower has moved this far, or after this long.
GPS_MIN_MOVE_METERS = 1.0
GPS_MIN_INTERVAL_SECONDS = 10.0

# Per-zone "last mowed" tracking. The mower's pose arrives at ~2 Hz; checking
# which zone it stands in that often is pointless, so presence is sampled on
# this interval. A zone's stamp is the last time the mower was observed inside
# it — a fact the device reported, not an inferred mowing schedule.
ZONE_PRESENCE_SAMPLE_SECONDS = 5.0
