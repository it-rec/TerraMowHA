"""TerraMow map rendering.

PIL rendering layer of the map camera: the theme palettes, layout constants,
font/placeholder caches and the ``MapRenderer`` that draws a scene built by
map_scene.py into the final PNG frame. No Home Assistant entity plumbing here
— the camera entity in camera.py owns callbacks, caching and attributes and
delegates all drawing to its ``MapRenderer``.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .map_scene import (
    coerce_angle_radians,
    coerce_float,
    coerce_int,
    point_tuple,
    simplify_path_pixels,
)
from .map_strings import hud_strings, resolve_language

# Output canvas
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1024

# Geometry (map scene) is rendered at this multiple of the canvas size and
# downsampled with LANCZOS, which anti-aliases polygon and path edges. Text is
# rasterized by FreeType (already anti-aliased) and stays at 1x.
SCENE_SUPERSAMPLE = 2

# Physical dimensions used to draw the robot, station and mowed swath at true
# scale. Map/path coordinates are millimetres (see docs/en/developers/map_path.md).
ROBOT_LENGTH_MM = 600
ROBOT_WIDTH_MM = 430
STATION_LENGTH_MM = 600
STATION_WIDTH_MM = 450
# Approximate blade-deck cutting width across current TerraMow models.
CUTTING_WIDTH_MM = 320

# On-canvas size clamps (1x pixels) so the icons stay legible on huge lawns and
# don't dwarf tiny test maps.
ROBOT_MIN_PX = 18
ROBOT_MAX_PX = 90
STATION_MIN_PX = 16
STATION_MAX_PX = 80

# Candidate scale-bar lengths in millimetres (0.1 m … 50 m). The renderer picks
# the largest one that fits SCALE_BAR_TARGET_PX so the bar shows a round number.
SCALE_BAR_STEPS_MM = (100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000)
SCALE_BAR_TARGET_PX = 200

# Layout
OUTER_MARGIN = 40
MAP_RECT = (40, 40, 984, 728)
SUMMARY_RECT = (40, 760, 984, 928)
MAP_PADDING = 24
# Reserved band at the top of the map card for the name/state chips, so the map
# geometry is fit below them instead of running up against (or under) the chips.
MAP_HEADER = 84
MAP_RADIUS = 28
CARD_RADIUS = 24

# Color definitions
COLOR_APP_BG = (237, 240, 244, 255)
COLOR_MAP_BG = (244, 244, 246, 255)
COLOR_CARD_BG = (255, 255, 255, 255)
COLOR_CARD_BORDER = (223, 227, 233, 255)
COLOR_SHADOW = (205, 212, 223, 90)
COLOR_TEXT = (38, 38, 38, 255)
COLOR_TEXT_SUBTLE = (102, 110, 122, 255)
COLOR_TEXT_MUTED = (149, 156, 166, 255)
COLOR_TEXT_WHITE = (255, 255, 255, 255)

COLOR_MAP_DEFAULT_FILL = (220, 224, 232, 255)
COLOR_MAP_DEFAULT_OUTLINE = (198, 199, 204, 255)
COLOR_CHANNEL = (255, 196, 0, 255)
COLOR_CHANNEL_SOFT = (255, 247, 219, 160)
COLOR_RESTRICTED_FILL = (255, 120, 70, 26)
COLOR_RESTRICTED_OUTLINE = (255, 120, 70, 255)
COLOR_PASS_THROUGH_FILL = (255, 162, 49, 36)
COLOR_PASS_THROUGH_OUTLINE = (255, 162, 49, 255)
COLOR_REQUIRED_FILL = (68, 117, 235, 32)
COLOR_REQUIRED_OUTLINE = (68, 117, 235, 255)
COLOR_DRAW_REGION_FILL = (68, 117, 235, 20)
COLOR_DRAW_REGION_OUTLINE = (68, 117, 235, 220)
COLOR_OBSTACLE_FILL = (98, 102, 109, 160)
COLOR_OBSTACLE_OUTLINE = (65, 69, 77, 255)
COLOR_EDGE_LINE = (176, 181, 190, 220)
COLOR_PATH_HISTORY = (48, 220, 187, 88)
COLOR_PATH_HISTORY_GLOW = (48, 220, 187, 52)
COLOR_PATH_CURRENT = (18, 191, 143, 132)
COLOR_PATH_CURRENT_GLOW = (18, 191, 143, 78)
COLOR_ORIGIN = (38, 38, 38, 180)

COLOR_ROBOT_BODY = (46, 46, 47, 255)
COLOR_ROBOT_TOP = (208, 211, 214, 255)
COLOR_ROBOT_DETAIL = (169, 174, 179, 255)
COLOR_ROBOT_DIR = (38, 38, 38, 255)

COLOR_STATION_BODY = (45, 45, 45, 255)
COLOR_STATION_TOP = (237, 239, 240, 255)
COLOR_STATION_LED = (51, 255, 92, 255)
COLOR_STATION_BORDER = (190, 194, 197, 255)

COLOR_BADGE_RED = (169, 37, 43, 255)
COLOR_BADGE_BLUE = (68, 117, 235, 255)
COLOR_BADGE_ORANGE = (255, 120, 70, 255)
COLOR_BADGE_GRAY = (108, 114, 124, 255)

COLOR_TRANSPARENT = (255, 255, 255, 0)

COLOR_PLACEHOLDER_BG = (200, 200, 200, 255)
COLOR_HATCH = (255, 120, 70, 88)
COLOR_COVERAGE = (20, 130, 105, 107)

RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class MapPalette:
    """Color palette for one map theme; defaults are the light theme."""

    app_bg: RGBA = COLOR_APP_BG
    map_bg: RGBA = COLOR_MAP_BG
    card_bg: RGBA = COLOR_CARD_BG
    card_border: RGBA = COLOR_CARD_BORDER
    shadow: RGBA = COLOR_SHADOW
    text: RGBA = COLOR_TEXT
    text_subtle: RGBA = COLOR_TEXT_SUBTLE
    text_muted: RGBA = COLOR_TEXT_MUTED
    text_white: RGBA = COLOR_TEXT_WHITE
    map_fill: RGBA = COLOR_MAP_DEFAULT_FILL
    map_outline: RGBA = COLOR_MAP_DEFAULT_OUTLINE
    channel: RGBA = COLOR_CHANNEL
    channel_soft: RGBA = COLOR_CHANNEL_SOFT
    restricted_fill: RGBA = COLOR_RESTRICTED_FILL
    restricted_outline: RGBA = COLOR_RESTRICTED_OUTLINE
    pass_through_fill: RGBA = COLOR_PASS_THROUGH_FILL
    pass_through_outline: RGBA = COLOR_PASS_THROUGH_OUTLINE
    required_fill: RGBA = COLOR_REQUIRED_FILL
    required_outline: RGBA = COLOR_REQUIRED_OUTLINE
    draw_region_fill: RGBA = COLOR_DRAW_REGION_FILL
    draw_region_outline: RGBA = COLOR_DRAW_REGION_OUTLINE
    obstacle_fill: RGBA = COLOR_OBSTACLE_FILL
    obstacle_outline: RGBA = COLOR_OBSTACLE_OUTLINE
    edge_line: RGBA = COLOR_EDGE_LINE
    path_history: RGBA = COLOR_PATH_HISTORY
    path_history_glow: RGBA = COLOR_PATH_HISTORY_GLOW
    path_current: RGBA = COLOR_PATH_CURRENT
    path_current_glow: RGBA = COLOR_PATH_CURRENT_GLOW
    coverage: RGBA = COLOR_COVERAGE
    origin: RGBA = COLOR_ORIGIN
    robot_body: RGBA = COLOR_ROBOT_BODY
    robot_top: RGBA = COLOR_ROBOT_TOP
    robot_detail: RGBA = COLOR_ROBOT_DETAIL
    station_body: RGBA = COLOR_STATION_BODY
    station_top: RGBA = COLOR_STATION_TOP
    station_led: RGBA = COLOR_STATION_LED
    station_border: RGBA = COLOR_STATION_BORDER
    badge_red: RGBA = COLOR_BADGE_RED
    badge_blue: RGBA = COLOR_BADGE_BLUE
    badge_orange: RGBA = COLOR_BADGE_ORANGE
    badge_gray: RGBA = COLOR_BADGE_GRAY
    placeholder_bg: RGBA = COLOR_PLACEHOLDER_BG
    hatch: RGBA = COLOR_HATCH


LIGHT_PALETTE = MapPalette()

DARK_PALETTE = replace(
    LIGHT_PALETTE,
    app_bg=(22, 25, 30, 255),
    map_bg=(30, 34, 40, 255),
    card_bg=(38, 43, 51, 255),
    card_border=(56, 62, 72, 255),
    shadow=(0, 0, 0, 110),
    text=(232, 234, 238, 255),
    text_subtle=(165, 172, 182, 255),
    text_muted=(125, 132, 143, 255),
    map_fill=(46, 52, 62, 255),
    map_outline=(86, 93, 105, 255),
    channel_soft=(255, 196, 0, 56),
    restricted_fill=(255, 120, 70, 44),
    pass_through_fill=(255, 162, 49, 52),
    required_fill=(88, 134, 245, 56),
    required_outline=(110, 150, 250, 255),
    draw_region_fill=(88, 134, 245, 40),
    draw_region_outline=(110, 150, 250, 230),
    obstacle_fill=(125, 130, 140, 150),
    obstacle_outline=(170, 175, 185, 255),
    edge_line=(110, 117, 128, 220),
    coverage=(26, 150, 122, 107),
    origin=(232, 234, 238, 180),
    placeholder_bg=(38, 43, 51, 255),
)

PALETTES = {"light": LIGHT_PALETTE, "dark": DARK_PALETTE}


@lru_cache(maxsize=32)
def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font."""
    candidates = [
        (
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ),
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
    ]
    for regular_path, bold_path in candidates:
        font_path = bold_path if bold else regular_path
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


class CoordinateTransformer:
    """Converts map coordinates (mm) to canvas pixel coordinates."""

    def __init__(
        self,
        bounds: tuple[float, float, float, float] | None,
        rect: tuple[int, int, int, int],
        padding: int = MAP_PADDING,
    ) -> None:
        """Fit the scene's bounding box into ``rect``.

        ``bounds`` is ``(min_x, min_y, max_x, max_y)`` in map units, or None
        when the scene has no geometry at all. It used to be the scene's full
        point list, which the fit only ever reduced to these four numbers;
        ``map_scene.build_scene`` now accumulates the box directly (see
        ``_BoundsAccumulator``) instead of materializing and deduplicating
        every path point on each rebuild.
        """
        self.left, self.top, self.right, self.bottom = rect
        self.padding = padding
        self._usable_width = max(1.0, float(self.right - self.left - 2 * padding))
        self._usable_height = max(1.0, float(self.bottom - self.top - 2 * padding))
        self._scale = 1.0
        self._offset_x = float(self.left + padding)
        self._offset_y = float(self.top + padding)

        if bounds is None:
            return

        min_x, min_y, max_x, max_y = bounds

        range_x = max(1.0, max_x - min_x)
        range_y = max(1.0, max_y - min_y)
        self._scale = min(self._usable_width / range_x, self._usable_height / range_y)
        content_w = range_x * self._scale
        content_h = range_y * self._scale
        self._offset_x = (
            self.left
            + padding
            + (self._usable_width - content_w) / 2
            - min_x * self._scale
        )
        self._offset_y = (
            self.top
            + padding
            + (self._usable_height - content_h) / 2
            - min_y * self._scale
        )

    @property
    def scale(self) -> float:
        """Pixels per map unit (mm)."""
        return self._scale

    def to_pixel(self, x: float, y: float) -> tuple[int, int]:
        """Convert a map coordinate to a pixel coordinate (scaling and translation only)."""
        px = int(round(x * self._scale + self._offset_x))
        py = int(round(y * self._scale + self._offset_y))
        return px, py

    def to_map(self, px: float, py: float) -> tuple[float, float]:
        """Convert a pixel coordinate back to a map coordinate."""
        return (
            (px - self._offset_x) / self._scale,
            (py - self._offset_y) / self._scale,
        )

    def to_pixels(self, points: list[tuple[float, float]]) -> list[tuple[int, int]]:
        """Convert coordinates in bulk."""
        return [self.to_pixel(point[0], point[1]) for point in points]


def _enum_label(value: Any) -> str:
    """Convert an enum string into shorter, human-readable text."""
    if not isinstance(value, str) or not value:
        return "-"
    replacements = {
        "MAP_CLEAN_INFO_MODE_": "",
        "MAP_STATE_": "",
        "NAVIGATION_PATH_TYPE_": "",
        "PATH_POINT_TYPE_": "",
        "MAP_TYPE_": "",
        "HIGH_GRASS_EDGE_TRIM_": "",
        "MOW_SPEED_TYPE_": "",
        "BLADE_DISK_SPEED_TYPE_": "",
        "MAIN_DIRECTION_MODE_": "",
    }
    text = value
    for prefix, replacement in replacements.items():
        if text.startswith(prefix):
            text = replacement + text[len(prefix):]
            break
    return text.replace("_", " ").title()


def _truncate(text: str, max_length: int) -> str:
    """Truncate a string."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _format_area(total_area_tenths: Any) -> str:
    """Format an area value.

    Uses ``m²`` (ASCII m + superscript two) rather than the single CJK glyph
    ``㎡`` (U+33A1), which many of the fonts we fall back to can't render and
    would draw as a tofu box.
    """
    area = coerce_float(total_area_tenths)
    if area is None:
        return "-"
    return f"{area / 10:.1f} m²"


def _format_file_size(value: Any) -> str:
    """Format a file size."""
    size = coerce_float(value)
    if size is None:
        return "-"
    units = ["B", "KB", "MB", "GB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)}{units[index]}"
    return f"{size:.1f}{units[index]}"


def _format_point(point: tuple[float, float] | None) -> str:
    """Format a point."""
    if point is None:
        return "-"
    return f"{int(round(point[0]))}, {int(round(point[1]))}"


def _format_size(map_data: dict[str, Any]) -> str:
    """Format size information."""
    width = coerce_int(map_data.get("width"))
    height = coerce_int(map_data.get("height"))
    resolution = coerce_int(map_data.get("resolution"))
    if width is None or height is None or resolution is None:
        return "-"
    return f"{width}×{height} @ {resolution}mm"


# Cached per (text, palette) — i.e. per UI language and theme — so repeated
# waiting-for-data polls don't re-render and re-encode the same placeholder.
@lru_cache(maxsize=8)
def render_placeholder(
    text: str = "Waiting for map data...",
    palette: MapPalette = LIGHT_PALETTE,
) -> bytes:
    """Generate a placeholder image."""
    image = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), palette.placeholder_bg[:3])
    draw = ImageDraw.Draw(image)
    title_font = _load_font(28, bold=True)
    text_font = _load_font(18)
    title = "TerraMow Map"
    title_box = draw.textbbox((0, 0), title, font=title_font)
    text_box = draw.textbbox((0, 0), text, font=text_font)
    title_w = title_box[2] - title_box[0]
    title_h = title_box[3] - title_box[1]
    text_w = text_box[2] - text_box[0]
    center_x = IMAGE_WIDTH / 2
    center_y = IMAGE_HEIGHT / 2
    draw.text(
        (center_x - title_w / 2, center_y - title_h - 8),
        title,
        fill=palette.text,
        font=title_font,
    )
    draw.text(
        (center_x - text_w / 2, center_y + 8),
        text,
        fill=palette.text_subtle,
        font=text_font,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class MapRenderer:
    """Draws map scenes into PNG frames for one camera entity.

    Owns the presentation state — palette, HUD language, layout mode and
    output resolution — plus the transient drawing state: the active
    coordinate transformer, the scene-scale factor and the cached robot
    sprite. The camera entity feeds it scenes built by map_scene.py and keeps
    all Home Assistant plumbing (callbacks, caching, attributes) to itself.
    """

    def __init__(
        self,
        *,
        theme: str,
        language: str | None,
        clean_mode: bool,
        show_coverage: bool,
        output_resolution: int,
    ) -> None:
        self._clean_mode = clean_mode
        self._show_coverage = show_coverage
        self._output_resolution = output_resolution
        self._palette = PALETTES[theme]
        self._map_rect: tuple[int, int, int, int] = (
            (0, 0, IMAGE_WIDTH, IMAGE_HEIGHT) if clean_mode else MAP_RECT
        )
        # HUD label table for the Home Assistant UI language (English-filled).
        self._language = resolve_language(language)
        self._hud = hud_strings(language)
        # Cached robot sprite as one atomic (icon, mask, length_px) triple so
        # concurrent renders in executor threads never see a torn icon; it is
        # rebuilt when the map scale changes the on-canvas length.
        self._robot_icon: tuple[Image.Image, Image.Image, int] | None = None
        # Scale factor applied to line widths / marker sizes while the scene is
        # drawn onto the supersampled canvas (1 outside of scene drawing).
        self._scene_scale = 1
        self._transformer: CoordinateTransformer | None = None
        # Supersampled canvas checkpointed after the static prefix
        # (_draw_scene_static), keyed on the exact map_data dict identity and
        # the transformer fit. Path pushes then redraw only the overlay
        # suffix. Trade-off: keeps one supersampled RGBA canvas (~16 MB at
        # the default resolution) alive while map data is present.
        self._static_checkpoint: (
            tuple[dict[str, Any], float, float, float, Image.Image] | None
        ) = None

    @property
    def language(self) -> str:
        """The resolved HUD language code."""
        return self._language

    def reset(self) -> None:
        """Forget the transformer when there is no scene left to draw."""
        self._transformer = None
        self._static_checkpoint = None

    def placeholder_png(self) -> bytes:
        """The waiting-for-data placeholder in this renderer's theme/language."""
        return render_placeholder(self._t("waiting"), palette=self._palette)

    def render_static(
        self,
        scene: dict[str, Any],
        map_data: dict[str, Any],
        last_update_label: str | None,
    ) -> tuple[Image.Image, CoordinateTransformer | None]:
        """Render the static layers; returns the image with its transformer."""
        bg_color = (0, 0, 0, 0) if self._clean_mode else self._palette.app_bg
        image = Image.new("RGBA", (IMAGE_WIDTH, IMAGE_HEIGHT), bg_color)
        if not self._clean_mode:
            self._draw_background(image)

        if scene["bounds"] is not None:
            # The scene geometry is drawn onto a supersampled transparent
            # canvas and downsampled onto the card, anti-aliasing polygon and
            # path edges. Widths/marker sizes are scaled via self._s() while
            # self._scene_scale is active.
            ss = SCENE_SUPERSAMPLE
            padding = 0 if self._clean_mode else MAP_PADDING
            # Fit the geometry below the chip header band (full mode only) so
            # the map never runs up against the name/state chips.
            header = 0 if self._clean_mode else MAP_HEADER
            fit_rect = (
                self._map_rect[0],
                self._map_rect[1] + header,
                self._map_rect[2],
                self._map_rect[3],
            )
            self._scene_scale = ss
            self._transformer = CoordinateTransformer(
                scene["bounds"],
                (
                    fit_rect[0] * ss,
                    fit_rect[1] * ss,
                    fit_rect[2] * ss,
                    fit_rect[3] * ss,
                ),
                padding=padding * ss,
            )
            # The static prefix depends only on map_data and the fit; new
            # path points arrive far more often than either changes (a point
            # outside the previous bounds changes the fit and misses). On a
            # hit, replay the checkpointed canvas and redraw just the overlay
            # suffix — pixel-identical to a full redraw because the same
            # operations run in the same order on identical canvas state.
            checkpoint = self._static_checkpoint
            ss_transformer = self._transformer
            try:
                if (
                    checkpoint is not None
                    and checkpoint[0] is map_data
                    and checkpoint[1] == ss_transformer._scale
                    and checkpoint[2] == ss_transformer._offset_x
                    and checkpoint[3] == ss_transformer._offset_y
                ):
                    scene_canvas = checkpoint[4].copy()
                else:
                    scene_canvas = Image.new(
                        "RGBA", (IMAGE_WIDTH * ss, IMAGE_HEIGHT * ss), (0, 0, 0, 0)
                    )
                    self._draw_scene_static(scene_canvas, scene)
                    self._static_checkpoint = (
                        map_data,
                        ss_transformer._scale,
                        ss_transformer._offset_x,
                        ss_transformer._offset_y,
                        scene_canvas.copy(),
                    )
                self._draw_scene_overlay(scene_canvas, scene)
            finally:
                self._scene_scale = 1
            image.alpha_composite(
                scene_canvas.resize(
                    (IMAGE_WIDTH, IMAGE_HEIGHT), Image.Resampling.LANCZOS
                )
            )
            # Live overlays (robot) and calibration attributes work in 1x
            # canvas pixels; both transformers describe the same fit because
            # every rect/padding input scales linearly with ss.
            self._transformer = CoordinateTransformer(
                scene["bounds"],
                fit_rect,
                padding=padding,
            )
            if not self._clean_mode:
                chip_draw = ImageDraw.Draw(image, "RGBA")
                self._draw_map_chips(chip_draw, map_data)
                self._draw_scale_bar(chip_draw)
                self._draw_legend(chip_draw, scene)
        else:
            self._transformer = None
            self._static_checkpoint = None
            self._draw_empty_map_card(image, map_data)

        if not self._clean_mode:
            self._draw_summary_panel(image, scene, map_data, last_update_label)
        return (image, self._transformer)

    def compose_frame(
        self,
        snapshot: tuple[Image.Image, CoordinateTransformer | None],
        display_pose: dict[str, Any] | None,
    ) -> bytes:
        """Compose the live frame from a static snapshot and encode it as PNG."""
        static_image, transformer = snapshot
        image = static_image.copy()
        self._draw_robot(image, transformer, display_pose)

        if self._output_resolution != IMAGE_WIDTH:
            image = image.resize(
                (self._output_resolution, self._output_resolution),
                Image.Resampling.LANCZOS,
            )

        buffer = io.BytesIO()
        if self._clean_mode:
            image.save(buffer, format="PNG")
        else:
            image.convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue()

    def _s(self, value: float) -> int:
        """Scale a 1x pixel dimension to the active scene canvas scale."""
        return max(1, int(round(value * self._scene_scale)))

    def _t(self, key: str) -> str:
        """Return the localized HUD label for a key (English-filled)."""
        return self._hud.get(key, key)

    def _draw_background(self, image: Image.Image) -> None:
        """Draw the canvas background and cards."""
        pal = self._palette
        draw = ImageDraw.Draw(image, "RGBA")
        # Shadow first, then the card fill with its border on top, so the
        # border is not overdrawn by a later fill.
        draw.rounded_rectangle(
            (MAP_RECT[0], MAP_RECT[1] + 10, MAP_RECT[2], MAP_RECT[3] + 10),
            radius=MAP_RADIUS,
            fill=pal.shadow,
        )
        draw.rounded_rectangle(MAP_RECT, radius=MAP_RADIUS, fill=pal.map_bg, outline=pal.card_border)
        draw.rounded_rectangle(
            (SUMMARY_RECT[0], SUMMARY_RECT[1] + 10, SUMMARY_RECT[2], SUMMARY_RECT[3] + 10),
            radius=CARD_RADIUS,
            fill=pal.shadow,
        )
        draw.rounded_rectangle(SUMMARY_RECT, radius=CARD_RADIUS, fill=pal.card_bg)

    def _draw_empty_map_card(self, image: Image.Image, map_data: dict[str, Any]) -> None:
        """Empty map shown when there is no spatial data."""
        draw = ImageDraw.Draw(image, "RGBA")
        title_font = _load_font(28, bold=True)
        body_font = _load_font(18)
        title = map_data.get("name") or "TerraMow Map"
        subtitle = self._t("empty_subtitle")
        title_box = draw.textbbox((0, 0), title, font=title_font)
        body_box = draw.textbbox((0, 0), subtitle, font=body_font)
        center_x = (self._map_rect[0] + self._map_rect[2]) / 2
        center_y = (self._map_rect[1] + self._map_rect[3]) / 2
        draw.text(
            (center_x - (title_box[2] - title_box[0]) / 2, center_y - 24),
            title,
            fill=self._palette.text,
            font=title_font,
        )
        draw.text(
            (center_x - (body_box[2] - body_box[0]) / 2, center_y + 12),
            subtitle,
            fill=self._palette.text_subtle,
            font=body_font,
        )
        if not self._clean_mode:
            self._draw_map_chips(draw, map_data)

    def _draw_scene(self, image: Image.Image, scene: dict[str, Any]) -> None:
        """Draw the complete scene."""
        self._draw_scene_static(image, scene)
        self._draw_scene_overlay(image, scene)

    def _draw_scene_static(self, image: Image.Image, scene: dict[str, Any]) -> None:
        """Draw the scene prefix that depends on map_data alone.

        Map extent and regions change only when a new ha_map_v1 dict arrives,
        so ``render_static`` checkpoints the canvas after this prefix and
        replays it for path-only updates (see ``_static_checkpoint``). Keep
        anything derived from path data out of this method.
        """
        pal = self._palette
        draw = ImageDraw.Draw(image, "RGBA")
        transformer = self._transformer
        if transformer is None:
            return

        if scene["map_extent"]:
            pixels = transformer.to_pixels(scene["map_extent"])
            draw.polygon(
                pixels,
                fill=pal.map_fill,
                outline=pal.map_outline,
            )

        for region in scene["regions"]:
            for sub_region in region["sub_regions"]:
                boundary = sub_region["boundary"]
                if len(boundary) < 3:
                    continue
                pixels = transformer.to_pixels(boundary)
                fill = pal.required_fill if sub_region["selected"] else pal.map_fill
                outline = (
                    pal.required_outline if sub_region["selected"] else pal.map_outline
                )
                self._draw_polygon_pixels(image, draw, pixels, fill, outline, self._s(1))
                for inner in sub_region["inner_boundaries"]:
                    inner_pixels = transformer.to_pixels(inner)
                    draw.polygon(
                        inner_pixels,
                        fill=pal.map_bg,
                        outline=pal.map_outline,
                    )
                for edge_line in sub_region["edge_lines"]:
                    self._draw_polyline(draw, transformer, edge_line, pal.edge_line, self._s(2))
                center = sub_region["center"]
                if center is not None and sub_region["order"] and sub_region["order"] > 0:
                    self._draw_order_badge(draw, transformer.to_pixel(center[0], center[1]), sub_region["order"])
                if center is not None and sub_region["has_custom_param"]:
                    center_px = transformer.to_pixel(center[0], center[1])
                    draw.ellipse(
                        [
                            center_px[0] + self._s(12),
                            center_px[1] - self._s(18),
                            center_px[0] + self._s(22),
                            center_px[1] - self._s(8),
                        ],
                        fill=pal.pass_through_outline,
                        outline=pal.text_white,
                        width=self._s(2),
                    )

            if len(region["boundary"]) >= 3:
                pixels = transformer.to_pixels(region["boundary"])
                draw.line(pixels + [pixels[0]], fill=pal.map_outline, width=self._s(2))
            for edge_line in region["edge_lines"]:
                self._draw_polyline(draw, transformer, edge_line, pal.edge_line, self._s(2))

    def _draw_scene_overlay(self, image: Image.Image, scene: dict[str, Any]) -> None:
        """Draw the scene suffix atop the static prefix.

        Runs on every rebuild (path pushes land here); the draw order within
        the suffix — coverage/path first, zones and markers above them — is
        part of the rendered output and must not change.
        """
        pal = self._palette
        draw = ImageDraw.Draw(image, "RGBA")
        transformer = self._transformer
        if transformer is None:
            return

        if self._show_coverage:
            self._draw_coverage(image, scene)
        self._draw_path(image, scene)

        for polygon in scene["required_zones"]:
            self._draw_polygon(image, draw, transformer, polygon, pal.required_fill, pal.required_outline, self._s(3))

        for polygon in scene["pass_through_zones"]:
            self._draw_polygon(
                image,
                draw,
                transformer,
                polygon,
                pal.pass_through_fill,
                pal.pass_through_outline,
                self._s(3),
            )

        for polygon in scene["forbidden_zones"]:
            self._draw_polygon(
                image,
                draw,
                transformer,
                polygon,
                pal.restricted_fill,
                pal.restricted_outline,
                self._s(3),
            )

        for polygon in scene["physical_forbidden_zones"]:
            self._draw_polygon(
                image,
                draw,
                transformer,
                polygon,
                pal.restricted_fill,
                pal.restricted_outline,
                self._s(4),
            )
            self._apply_hatch(image, transformer.to_pixels(polygon), pal.hatch, spacing=self._s(12))

        for polygon in scene["obstacles"]:
            self._draw_polygon(
                image,
                draw,
                transformer,
                polygon,
                pal.obstacle_fill,
                pal.obstacle_outline,
                self._s(2),
            )

        for polygon in scene["draw_region_polygons"]:
            pixels = transformer.to_pixels(polygon)
            self._composite_polygon_fill(image, pixels, pal.draw_region_fill)
            self._draw_dashed_polyline(draw, pixels + [pixels[0]], pal.draw_region_outline, self._s(3), self._s(12), self._s(8))

        for wall in scene["virtual_walls"]:
            pixels = transformer.to_pixels(wall)
            self._draw_dashed_polyline(draw, pixels, pal.restricted_outline, self._s(4), self._s(12), self._s(8))

        for tunnel in scene["cross_boundary_tunnels"]:
            self._draw_tunnel(image, draw, transformer, tunnel, pal.channel_soft, pal.channel)
        for tunnel in scene["virtual_cross_boundary_tunnels"]:
            self._draw_tunnel(image, draw, transformer, tunnel, pal.channel_soft, pal.channel)

        for marker in scene["cross_boundary_markers"]:
            self._draw_marker(draw, transformer.to_pixel(marker[0], marker[1]), pal.channel, "diamond")
        for marker in scene["trapped_points"]:
            self._draw_marker(draw, transformer.to_pixel(marker[0], marker[1]), pal.badge_orange, "triangle")
        for marker in scene["maintenance_points"]:
            self._draw_marker(draw, transformer.to_pixel(marker[0], marker[1]), pal.badge_blue, "hex")

        if scene["move_target_point"] is not None:
            self._draw_target(draw, transformer.to_pixel(scene["move_target_point"][0], scene["move_target_point"][1]))

        if scene["station_pose"] is not None:
            self._draw_station(image, scene["station_pose"])

    @staticmethod
    def _overlay_bbox(
        image: Image.Image,
        points: list[tuple[int, int]],
        pad: int,
    ) -> tuple[int, int, int, int] | None:
        """Padded bounding box of the points, clamped to the canvas.

        Returns (left, top, right, bottom) with an exclusive right/bottom, or
        None when the shape lies entirely outside the canvas.
        """
        left = max(0, min(point[0] for point in points) - pad)
        top = max(0, min(point[1] for point in points) - pad)
        right = min(image.width, max(point[0] for point in points) + pad + 1)
        bottom = min(image.height, max(point[1] for point in points) + pad + 1)
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom

    def _composite_draw(
        self,
        image: Image.Image,
        points: list[tuple[int, int]],
        draw_fn: Any,
        pad: int = 1,
    ) -> None:
        """Draw on a transparent layer, then composite it onto the main image.

        The layer only spans the points' bounding box (padded by ``pad`` for
        line widths and end caps) instead of the full supersampled canvas, so
        translucent fills stay cheap per shape. ``draw_fn`` receives the
        overlay draw context and the points translated into overlay
        coordinates; the result composites back at the box offset, which is
        pixel-identical to drawing on a full-canvas overlay.
        """
        if not points:
            return
        bbox = self._overlay_bbox(image, points, pad)
        if bbox is None:
            return
        left, top, right, bottom = bbox
        overlay = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay, "RGBA")
        draw_fn(overlay_draw, [(x - left, y - top) for x, y in points])
        image.alpha_composite(overlay, (left, top))

    def _composite_polygon_fill(
        self,
        image: Image.Image,
        polygon_pixels: list[tuple[int, int]],
        fill: tuple[int, int, int, int],
    ) -> None:
        """Perform proper alpha compositing for the polygon fill."""
        self._composite_draw(
            image,
            polygon_pixels,
            lambda overlay_draw, shifted: overlay_draw.polygon(shifted, fill=fill),
        )

    def _draw_polygon_pixels(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        pixels: list[tuple[int, int]],
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int],
        width: int,
    ) -> None:
        """Draw a polygon from pixel points; composite the fill separately and draw the outline directly."""
        if len(pixels) < 3:
            return
        if fill[3] > 0:
            self._composite_polygon_fill(image, pixels, fill)
        draw.line(pixels + [pixels[0]], fill=outline, width=max(1, width))

    def _draw_polygon(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        transformer: CoordinateTransformer,
        polygon: list[tuple[float, float]],
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int],
        width: int,
    ) -> None:
        """Draw a filled polygon."""
        if len(polygon) < 3:
            return
        pixels = transformer.to_pixels(polygon)
        self._draw_polygon_pixels(image, draw, pixels, fill, outline, width)

    def _draw_polyline(
        self,
        draw: ImageDraw.ImageDraw,
        transformer: CoordinateTransformer,
        polyline: list[tuple[float, float]],
        color: tuple[int, int, int, int],
        width: int,
    ) -> None:
        """Draw a polyline."""
        if len(polyline) < 2:
            return
        draw.line(transformer.to_pixels(polyline), fill=color, width=width)

    def _draw_dashed_polyline(
        self,
        draw: ImageDraw.ImageDraw,
        points: list[tuple[int, int]],
        color: tuple[int, int, int, int],
        width: int,
        dash: int,
        gap: int,
    ) -> None:
        """Draw a dashed line."""
        if len(points) < 2:
            return
        for start, end in zip(points, points[1:], strict=False):
            x1, y1 = start
            x2, y2 = end
            dx = x2 - x1
            dy = y2 - y1
            distance = math.hypot(dx, dy)
            if distance == 0:
                continue
            step_x = dx / distance
            step_y = dy / distance
            position = 0.0
            while position < distance:
                dash_end = min(distance, position + dash)
                draw.line(
                    (
                        x1 + step_x * position,
                        y1 + step_y * position,
                        x1 + step_x * dash_end,
                        y1 + step_y * dash_end,
                    ),
                    fill=color,
                    width=width,
                )
                position += dash + gap

    def _apply_hatch(
        self,
        image: Image.Image,
        polygon_pixels: list[tuple[int, int]],
        color: tuple[int, int, int, int],
        spacing: int = 12,
    ) -> None:
        """Overlay a diagonal hatch texture on a region."""
        if len(polygon_pixels) < 3:
            return
        bbox = self._overlay_bbox(image, polygon_pixels, 1)
        if bbox is None:
            return
        # The mask and hatch layers only span the polygon's bounding box; the
        # hatch geometry stays in canvas coordinates shifted by the box offset,
        # so the visible (masked) result is pixel-identical to a full-canvas
        # overlay.
        left, top, right, bottom = bbox
        size = (right - left, bottom - top)
        mask = Image.new("L", size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.polygon([(x - left, y - top) for x, y in polygon_pixels], fill=255)

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        min_x = min(point[0] for point in polygon_pixels)
        max_x = max(point[0] for point in polygon_pixels)
        min_y = min(point[1] for point in polygon_pixels)
        max_y = max(point[1] for point in polygon_pixels)

        start = min_x - (max_y - min_y) - spacing
        end = max_x + (max_y - min_y) + spacing
        for offset in range(int(start), int(end), spacing):
            overlay_draw.line(
                [
                    (offset - left, max_y + spacing - top),
                    (offset + (max_y - min_y) + spacing - left, min_y - spacing - top),
                ],
                fill=color,
                width=1,
            )

        image.alpha_composite(
            Image.composite(overlay, Image.new("RGBA", overlay.size), mask),
            (left, top),
        )

    def _draw_tunnel(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        transformer: CoordinateTransformer,
        tunnel: dict[str, Any],
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int],
    ) -> None:
        """Draw a cross-boundary tunnel."""
        s = self._s
        for polygon in tunnel.get("polygons", []):
            self._draw_polygon(image, draw, transformer, polygon, fill, outline, s(3))
        for polyline in tunnel.get("polylines", []):
            pixels = transformer.to_pixels(polyline)
            self._composite_draw(
                image,
                pixels,
                lambda overlay_draw, shifted: overlay_draw.line(
                    shifted, fill=fill, width=s(10)
                ),
                pad=s(10),
            )
            draw.line(pixels, fill=outline, width=s(5))
            for point in (pixels[0], pixels[-1]):
                draw.ellipse(
                    [point[0] - s(5), point[1] - s(5), point[0] + s(5), point[1] + s(5)],
                    fill=outline,
                )

    def _draw_marker(
        self,
        draw: ImageDraw.ImageDraw,
        center: tuple[int, int],
        color: tuple[int, int, int, int],
        kind: str,
    ) -> None:
        """Draw a point marker."""
        x, y = center
        s = self._s
        white = self._palette.text_white
        if kind == "diamond":
            points = [(x, y - s(8)), (x + s(8), y), (x, y + s(8)), (x - s(8), y)]
            draw.polygon(points, fill=color, outline=white)
        elif kind == "triangle":
            points = [(x, y - s(9)), (x + s(8), y + s(7)), (x - s(8), y + s(7))]
            draw.polygon(points, fill=color, outline=white)
            draw.text((x - s(2), y - s(5)), "!", fill=white, font=_load_font(s(12), bold=True))
        elif kind == "hex":
            points = [
                (x - s(7), y),
                (x - s(3), y - s(6)),
                (x + s(3), y - s(6)),
                (x + s(7), y),
                (x + s(3), y + s(6)),
                (x - s(3), y + s(6)),
            ]
            draw.polygon(points, fill=color, outline=white)
        else:
            draw.ellipse([x - s(6), y - s(6), x + s(6), y + s(6)], fill=color)

    def _draw_order_badge(
        self,
        draw: ImageDraw.ImageDraw,
        center: tuple[int, int],
        order: int,
    ) -> None:
        """Draw an order badge."""
        x, y = center
        s = self._s
        draw.ellipse(
            [x - s(16), y - s(16), x + s(16), y + s(16)],
            fill=self._palette.badge_red,
            outline=self._palette.text_white,
            width=s(2),
        )
        font = _load_font(s(16), bold=True)
        text = str(order)
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2 - s(1)),
            text,
            fill=self._palette.text_white,
            font=font,
        )

    def _draw_target(self, draw: ImageDraw.ImageDraw, center: tuple[int, int]) -> None:
        """Draw a target point."""
        x, y = center
        s = self._s
        blue = self._palette.badge_blue
        draw.ellipse([x - s(18), y - s(18), x + s(18), y + s(18)], outline=blue, width=s(3))
        draw.ellipse([x - s(10), y - s(10), x + s(10), y + s(10)], outline=blue, width=s(2))
        draw.ellipse([x - s(3), y - s(3), x + s(3), y + s(3)], fill=blue)

    def _draw_path_stroke(
        self,
        draw: ImageDraw.ImageDraw,
        pixels: list[tuple[int, int]],
        inner_color: tuple[int, int, int, int],
        inner_width: int,
        glow_color: tuple[int, int, int, int],
        glow_width: int,
        dash: int | None = None,
        gap: int | None = None,
    ) -> None:
        """Draw a path with a soft glow edge."""
        if len(pixels) < 2:
            return
        if dash is not None and gap is not None:
            self._draw_dashed_polyline(draw, pixels, glow_color, glow_width, dash, gap)
            self._draw_dashed_polyline(draw, pixels, inner_color, inner_width, dash, gap)
            return

        draw.line(pixels, fill=glow_color, width=glow_width, joint="curve")
        draw.line(pixels, fill=inner_color, width=inner_width, joint="curve")

        # joint="curve" already rounds the interior vertices, so only the two
        # endpoints need round caps — drawing a circle per vertex would be
        # O(N) ellipses for no visible gain on a long mowing track.
        glow_radius = max(1, glow_width // 2)
        inner_radius = max(1, inner_width // 2)
        for x, y in (pixels[0], pixels[-1]):
            draw.ellipse(
                [x - glow_radius, y - glow_radius, x + glow_radius, y + glow_radius],
                fill=glow_color,
            )
            draw.ellipse(
                [x - inner_radius, y - inner_radius, x + inner_radius, y + inner_radius],
                fill=inner_color,
            )

    def _draw_path_layer(
        self,
        image: Image.Image,
        path_points: list[dict[str, Any]],
        variant: str,
    ) -> None:
        """Draw a single path layer in the given variant style."""
        transformer = self._transformer
        if transformer is None or len(path_points) < 2:
            return

        if variant == "history":
            default_inner = self._palette.path_history
            default_glow = self._palette.path_history_glow
            default_inner_width = self._s(10)
            default_glow_width = self._s(16)
            simplify_epsilon = 1.1 * self._scene_scale
            simplify_min_segment = 1.2 * self._scene_scale
        else:
            default_inner = self._palette.path_current
            default_glow = self._palette.path_current_glow
            default_inner_width = self._s(12)
            default_glow_width = self._s(18)
            simplify_epsilon = 0.9 * self._scene_scale
            simplify_min_segment = 1.0 * self._scene_scale

        pixels = [transformer.to_pixel(point["x"], point["y"]) for point in path_points]
        pixels = simplify_path_pixels(pixels, simplify_epsilon, simplify_min_segment)
        if len(pixels) < 2:
            return

        self._composite_draw(
            image,
            pixels,
            lambda overlay_draw, shifted: self._draw_path_stroke(
                overlay_draw,
                shifted,
                default_inner,
                default_inner_width,
                default_glow,
                default_glow_width,
            ),
            pad=default_glow_width,
        )

    def _draw_coverage(self, image: Image.Image, scene: dict[str, Any]) -> None:
        """Shade the mowed swath at the real cutting width under the path lines."""
        transformer = self._transformer
        if transformer is None:
            return
        swath_px = int(round(CUTTING_WIDTH_MM * transformer.scale))
        # Keep the swath sane on degenerate/legacy coordinate scales: at least
        # a visible band, at most an eighth of the canvas.
        swath_px = max(self._s(3), min(swath_px, (IMAGE_WIDTH * self._scene_scale) // 8))
        color = self._palette.coverage
        radius = max(1, swath_px // 2)

        def draw_swath(
            overlay_draw: ImageDraw.ImageDraw, shifted: list[tuple[int, int]]
        ) -> None:
            overlay_draw.line(shifted, fill=color, width=swath_px, joint="curve")
            for x, y in (shifted[0], shifted[-1]):
                overlay_draw.ellipse(
                    [x - radius, y - radius, x + radius, y + radius], fill=color
                )

        # Each archived session segment is swathed on its own so no false
        # band is painted across the dock-and-resume gap (issue #214). The live
        # path is swathed per mowing run for the same reason: a transit leg
        # between two runs must not leave a false mowed band across the gap.
        for path_points in [
            *scene.get("session_path_segments", []),
            *self._path_runs(scene, "history"),
            *self._path_runs(scene, "current"),
        ]:
            if len(path_points) < 2:
                continue
            pixels = [
                transformer.to_pixel(point["x"], point["y"])
                for point in path_points
            ]
            pixels = simplify_path_pixels(
                pixels, 1.1 * self._scene_scale, 1.2 * self._scene_scale
            )
            if len(pixels) < 2:
                continue
            self._composite_draw(image, pixels, draw_swath, pad=swath_px)

    def _draw_path(self, image: Image.Image, scene: dict[str, Any]) -> None:
        """Draw the history path and current path tracks separately.

        Each path is split into contiguous mowing runs and every run is drawn
        as its own polyline. A run break marks where the mower stopped mowing
        to transit (or return to dock) — that leg was filtered out, so joining
        the two runs would paint a straight diagonal the mower never drove.
        """
        for run in self._path_runs(scene, "history"):
            self._draw_path_layer(image, run, "history")
        # Tracks mowed earlier in the running session, before a mid-session
        # recharge (issue #214): part of the current job, drawn one segment at
        # a time so no connector crosses the dock gap.
        for segment in scene.get("session_path_segments", []):
            self._draw_path_layer(image, segment, "current")
        for run in self._path_runs(scene, "current"):
            self._draw_path_layer(image, run, "current")

    @staticmethod
    def _path_runs(
        scene: dict[str, Any], variant: str
    ) -> list[list[dict[str, Any]]]:
        """The mowing runs for ``variant``, falling back to the flat list.

        ``build_scene`` always supplies ``<variant>_path_runs``; the fallback
        wraps the flat ``<variant>_path_points`` as a single run so a
        hand-built scene without the split still renders.
        """
        runs: list[list[dict[str, Any]]] | None = scene.get(
            f"{variant}_path_runs"
        )
        if runs is not None:
            return runs
        flat = scene.get(f"{variant}_path_points", [])
        return [flat] if flat else []

    def _station_pixel_size(self, transformer: CoordinateTransformer) -> tuple[int, int]:
        """Station icon size in pixels on the active canvas, true to scale."""
        length_px = STATION_LENGTH_MM * transformer.scale
        length_px = min(
            max(length_px, STATION_MIN_PX * self._scene_scale),
            STATION_MAX_PX * self._scene_scale,
        )
        width_px = length_px * (STATION_WIDTH_MM / STATION_LENGTH_MM)
        return int(round(width_px)), int(round(length_px))

    def _draw_station(self, image: Image.Image, pose: dict[str, float]) -> None:
        """Draw the base station."""
        transformer = self._transformer
        if transformer is None:
            return

        w, h = self._station_pixel_size(transformer)
        canvas = max(w, h) + 4
        x = y = canvas // 2
        hw = w / 2
        hh = h / 2

        station = Image.new('RGBA', (canvas, canvas), COLOR_TRANSPARENT)
        draw = ImageDraw.Draw(station, 'RGBA')

        body_box = [x - hw, y - hh, x + hw, y + hh]
        draw.rounded_rectangle(
            body_box,
            radius=hw * 0.7,
            fill=self._palette.station_body,
        )
        draw.rounded_rectangle(
            [x - hw * 0.72, y - hh * 0.55, x + hw * 0.72, y + hh * 0.67],
            radius=hw * 0.55,
            fill=self._palette.station_top,
            outline=self._palette.station_border,
            width=1,
        )
        draw.ellipse(
            [x - hw * 0.3, y - hh * 0.72, x + hw * 0.3, y - hh * 0.28],
            fill=self._palette.station_led,
        )

        station_mask = station.copy()
        draw_mask = ImageDraw.Draw(station_mask)
        draw_mask.rounded_rectangle(
            body_box,
            radius=hw * 0.7,
            fill=self._palette.station_body,
        )

        theta = coerce_angle_radians(pose.get("theta"), milli_radian=True)
        if theta is None:
            theta = 0.0
        deg = theta * 180 / math.pi
        deg = deg - 90

        station_rotated = station.rotate(-deg, expand=True, fillcolor=COLOR_TRANSPARENT)
        station_mask_rotated = station_mask.rotate(-deg, expand=True, fillcolor=COLOR_TRANSPARENT)

        cx, cy = transformer.to_pixel(pose["x"], pose["y"])

        image.paste(station_rotated,
                  (cx - station_rotated.width // 2, cy - station_rotated.height // 2),
                  station_mask_rotated)

    def _robot_pixel_length(self, transformer: CoordinateTransformer) -> int:
        """Robot icon length in 1x pixels, true to scale within the clamps."""
        length_px = ROBOT_LENGTH_MM * transformer.scale
        return int(round(min(max(length_px, ROBOT_MIN_PX), ROBOT_MAX_PX)))

    def _build_robot_icon(self, length_px: int) -> tuple[Image.Image, Image.Image, int]:
        """Build (and cache) the robot icon for the given on-canvas length.

        The icon is drawn at 2x and downsampled by the caller after rotation,
        which anti-aliases both the shape and the rotated edges. Icon, mask
        and length are built into locals and published as a single tuple so a
        concurrent render in another executor thread can't see a torn icon.
        """
        cached = self._robot_icon
        if cached is not None and cached[2] == length_px:
            return cached

        oversample = 2
        h = length_px * oversample
        w = int(round(h * (ROBOT_WIDTH_MM / ROBOT_LENGTH_MM)))
        canvas = h + 4
        px = py = canvas // 2
        hw = w / 2
        hh = h / 2

        robot_image = Image.new('RGBA', (canvas, canvas), COLOR_TRANSPARENT)
        draw = ImageDraw.Draw(robot_image, 'RGBA')

        body_box = [px - hw, py - hh, px + hw, py + hh]
        draw.ellipse(body_box, fill=self._palette.robot_body)
        draw.ellipse(
            [px - hw * 0.75, py - hh * 0.75, px + hw * 0.75, py + hh * 0.2],
            fill=self._palette.robot_top,
        )
        draw.rectangle(
            [px - hw * 0.87, py + hh * 0.25, px + hw * 0.87, py + hh * 0.6],
            fill=self._palette.robot_detail,
        )

        robot_mask = robot_image.copy()
        draw_mask = ImageDraw.Draw(robot_mask)
        draw_mask.ellipse(body_box, fill=self._palette.robot_body)
        icon = (robot_image, robot_mask, length_px)
        self._robot_icon = icon
        return icon

    def _draw_robot(
        self,
        image: Image.Image,
        transformer: CoordinateTransformer | None,
        display_pose: dict[str, Any] | None,
    ) -> None:
        """Draw the live robot position."""
        if transformer is None:
            return
        if display_pose is None:
            return

        x = display_pose["x"]
        y = display_pose["y"]

        robot_image, robot_mask, _ = self._build_robot_icon(
            self._robot_pixel_length(transformer)
        )

        yaw = display_pose.get("yaw")
        if yaw is None:
            yaw = 0

        cx, cy = transformer.to_pixel(x, y)

        deg = yaw * 180 / math.pi
        deg = deg - 90

        robot_rotated = robot_image.rotate(-deg, expand=True, fillcolor=COLOR_TRANSPARENT)
        robot_mask_rotated = robot_mask.rotate(-deg, expand=True, fillcolor=COLOR_TRANSPARENT)

        # Downsample the 2x icon after rotation for anti-aliased edges.
        target = (
            max(1, robot_rotated.width // 2),
            max(1, robot_rotated.height // 2),
        )
        robot_rotated = robot_rotated.resize(target, Image.Resampling.LANCZOS)
        robot_mask_rotated = robot_mask_rotated.resize(target, Image.Resampling.LANCZOS)

        image.paste(robot_rotated,
                  (cx - robot_rotated.width // 2, cy - robot_rotated.height // 2),
                  robot_mask_rotated)

    def _draw_map_chips(self, draw: ImageDraw.ImageDraw, map_data: dict[str, Any]) -> None:
        """Draw the summary chips above the map."""
        name = map_data.get("name") or f"Map #{map_data.get('id', '-')}"
        state = _enum_label(map_data.get("map_state"))

        pal = self._palette
        left = MAP_RECT[0] + 18
        top = MAP_RECT[1] + 18
        self._draw_chip(draw, (left, top), _truncate(name, 26), pal.card_bg, pal.text)
        badge_color = pal.badge_blue if "Complete" in state else pal.badge_orange if state != "-" else pal.badge_gray
        self._draw_chip(draw, (left, top + 42), state, badge_color, pal.text_white)

    def _scale_bar_choice(self, scale: float) -> tuple[int, int] | None:
        """Pick (length_mm, length_px) for the scale bar, or None if unusable.

        ``scale`` is 1x pixels per millimetre. The largest round distance whose
        bar stays within SCALE_BAR_TARGET_PX wins; if even the smallest step is
        too wide (extreme zoom), the bar is suppressed.
        """
        if scale <= 0:
            return None
        chosen_mm: int | None = None
        for step_mm in SCALE_BAR_STEPS_MM:
            length_px = step_mm * scale
            if length_px <= SCALE_BAR_TARGET_PX:
                chosen_mm = step_mm
            else:
                break
        if chosen_mm is None:
            return None
        length_px = int(round(chosen_mm * scale))
        if length_px < 12:
            return None
        return chosen_mm, length_px

    def _draw_scale_bar(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw a scale bar with a round metric distance in the map's corner."""
        transformer = self._transformer
        if transformer is None:
            return
        choice = self._scale_bar_choice(transformer.scale)
        if choice is None:
            return
        length_mm, length_px = choice

        pal = self._palette
        x0 = MAP_RECT[0] + 22
        y = MAP_RECT[3] - 26
        x1 = x0 + length_px
        draw.line([(x0, y), (x1, y)], fill=pal.text_subtle, width=3)
        for tick_x in (x0, x1):
            draw.line([(tick_x, y - 6), (tick_x, y + 6)], fill=pal.text_subtle, width=3)

        meters = length_mm / 1000
        label = f"{meters:g} m"
        font = _load_font(14, bold=True)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            (x0 + (length_px - (box[2] - box[0])) / 2, y - 24),
            label,
            fill=pal.text_subtle,
            font=font,
        )

    def _legend_entries(self, scene: dict[str, Any]) -> list[tuple[tuple[int, int, int, int], str]]:
        """Color/label pairs for the feature types present in the scene."""
        pal = self._palette
        counts = scene.get("scene_counts", {})
        entries: list[tuple[tuple[int, int, int, int], str]] = []
        has_mow_track = bool(
            scene.get("path_points") or scene.get("session_path_segments")
        )
        if has_mow_track:
            entries.append((pal.path_current, self._t("path")))
        if self._show_coverage and has_mow_track:
            entries.append((pal.coverage, self._t("coverage")))
        if counts.get("forbidden_zones", 0) or counts.get("physical_forbidden_zones", 0):
            entries.append((pal.restricted_outline, self._t("nogo")))
        if counts.get("required_zones", 0):
            entries.append((pal.required_outline, self._t("required")))
        if counts.get("pass_through_zones", 0):
            entries.append((pal.pass_through_outline, self._t("pass_through")))
        if counts.get("cross_boundary_tunnels", 0) or counts.get(
            "virtual_cross_boundary_tunnels", 0
        ):
            entries.append((pal.channel, self._t("tunnel")))
        if counts.get("obstacles", 0):
            entries.append((pal.obstacle_outline, self._t("obstacle")))
        return entries

    def _draw_legend(self, draw: ImageDraw.ImageDraw, scene: dict[str, Any]) -> None:
        """Draw a compact color legend in the map's top-right corner."""
        entries = self._legend_entries(scene)
        if not entries:
            return
        pal = self._palette
        font = _load_font(13, bold=True)
        row_height = 22
        swatch = 12
        text_gap = 8
        pad = 12
        text_width = max(
            (draw.textbbox((0, 0), label, font=font)[2] for _, label in entries),
            default=0,
        )
        box_width = pad * 2 + swatch + text_gap + text_width
        box_height = pad * 2 + row_height * len(entries) - (row_height - swatch)
        right = MAP_RECT[2] - 18
        top = MAP_RECT[1] + 18
        left = right - box_width

        overlay_color = (*pal.card_bg[:3], 220)
        draw.rounded_rectangle(
            [left, top, right, top + box_height],
            radius=12,
            fill=overlay_color,
            outline=pal.card_border,
        )
        y = top + pad
        for color, label in entries:
            draw.rounded_rectangle(
                [left + pad, y, left + pad + swatch, y + swatch],
                radius=3,
                fill=color,
            )
            draw.text(
                (left + pad + swatch + text_gap, y - 1),
                label,
                fill=pal.text,
                font=font,
            )
            y += row_height

    def _draw_chip(
        self,
        draw: ImageDraw.ImageDraw,
        location: tuple[int, int],
        text: str,
        fill: tuple[int, int, int, int],
        text_color: tuple[int, int, int, int],
    ) -> None:
        """Draw a rounded-corner chip."""
        x, y = location
        width = self._chip_width(text)
        height = 32
        font = _load_font(15, bold=True)
        draw.rounded_rectangle([x, y, x + width, y + height], radius=16, fill=fill)
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (x + (width - (box[2] - box[0])) / 2, y + (height - (box[3] - box[1])) / 2 - 1),
            text,
            fill=text_color,
            font=font,
        )

    def _chip_width(self, text: str) -> int:
        """Compute the chip width."""
        font = _load_font(15, bold=True)
        box = font.getbbox(text)
        return int(box[2] - box[0] + 24)

    def _draw_summary_panel(
        self,
        image: Image.Image,
        scene: dict[str, Any],
        map_data: dict[str, Any],
        last_update_label: str | None,
    ) -> None:
        """Draw the bottom summary panel."""
        draw = ImageDraw.Draw(image, "RGBA")
        left, top, right, bottom = SUMMARY_RECT
        width = right - left
        label_font = _load_font(13)
        value_font = _load_font(18, bold=True)
        chip_font = _load_font(13, bold=True)

        grid_top = top + 18
        grid_left = left + 22
        grid_width = width - 44
        cell_width = grid_width / 4
        cell_height = 42

        flags = []
        if map_data.get("has_bird_view"):
            flags.append(f"Bird {map_data.get('bird_view_index', 0)}")
        if map_data.get("enable_advanced_edge_cutting"):
            flags.append(self._t("flag_adv_edge"))
        flags.append(self._t("flag_locked") if map_data.get("is_boundary_locked") else self._t("flag_unlocked"))
        flags.append(self._t("flag_build_on") if map_data.get("is_able_to_run_build_map") else self._t("flag_build_off"))

        backup_info = map_data.get("backup_info_list", [])
        backup_text = self._t("backup_off")
        if map_data.get("has_backup") or backup_info:
            backup_text = f"{len(backup_info) if isinstance(backup_info, list) else 0} {self._t('backup_item')}"
        metrics = [
            (self._t("lbl_map"), _truncate(f"#{map_data.get('id', '-')} · {map_data.get('name', '-')}", 22)),
            (self._t("lbl_area"), _format_area(map_data.get("total_area"))),
            (self._t("lbl_mode"), _truncate(_enum_label(map_data.get("clean_info", {}).get("mode")), 20)),
            (self._t("lbl_size"), _truncate(_format_size(map_data), 24)),
            (self._t("lbl_origin"), _format_point(point_tuple(map_data.get("origin")))),
            (self._t("lbl_backup"), _truncate(f"{backup_text} · {_format_file_size(map_data.get('file_size'))}", 24)),
            (self._t("lbl_flags"), _truncate(" / ".join(flags), 24)),
        ]

        for index, (label, value) in enumerate(metrics):
            row = index // 4
            column = index % 4
            x = grid_left + column * cell_width
            y = grid_top + row * cell_height
            draw.text((x, y), label, fill=self._palette.text_muted, font=label_font)
            draw.text((x, y + 16), value, fill=self._palette.text, font=value_font)

        chip_y = bottom - 46
        chip_x = left + 22

        # The "Updated HH:MM" stamp sits at the bottom-right of the panel, on
        # the same row as the count chips, so it never collides with the metric
        # grid above (localized labels there can be wide).
        stamp_font = _load_font(13)
        stamp_right = right - 22
        chip_limit = stamp_right
        if last_update_label:
            stamp = f"{self._t('updated')} {last_update_label}"
            stamp_box = draw.textbbox((0, 0), stamp, font=stamp_font)
            stamp_width = int(stamp_box[2] - stamp_box[0])
            draw.text(
                (stamp_right - stamp_width, chip_y + 7),
                stamp,
                fill=self._palette.text_muted,
                font=stamp_font,
            )
            # keep the count chips clear of the stamp
            chip_limit = stamp_right - stamp_width - 16

        count_chips = [
            f"R {scene['scene_counts']['regions']}/{scene['scene_counts']['sub_regions']}",
            f"{self._t('nogo')} {scene['scene_counts']['forbidden_zones'] + scene['scene_counts']['physical_forbidden_zones']}",
            f"{self._t('pass_short')} {scene['scene_counts']['pass_through_zones']}",
            f"{self._t('tunnel')} {scene['scene_counts']['cross_boundary_tunnels'] + scene['scene_counts']['virtual_cross_boundary_tunnels']}",
        ]
        for chip in count_chips:
            box = draw.textbbox((0, 0), chip, font=chip_font)
            chip_width = int(box[2] - box[0]) + 20
            if chip_x + chip_width > chip_limit:
                break
            draw.rounded_rectangle(
                [chip_x, chip_y, chip_x + chip_width, chip_y + 28],
                radius=14,
                fill=self._palette.map_bg,
            )
            draw.text((chip_x + 10, chip_y + 6), chip, fill=self._palette.text_subtle, font=chip_font)
            chip_x += chip_width + 10


def _format_duration(minutes: float | None) -> str:
    """Render a minute count as ``1 h 45 min`` / ``45 min`` / ``—``."""
    if minutes is None or minutes < 0:
        return "—"
    total = int(round(minutes))
    hours, rest = divmod(total, 60)
    return f"{hours} h {rest} min" if hours else f"{rest} min"


def render_mow_report(
    scene: dict[str, Any],
    map_data: dict[str, Any],
    *,
    report: dict[str, Any],
    theme: str,
    language: str | None,
    output_resolution: int,
    finished_local: datetime,
) -> bytes:
    """Render the frozen report of a finished mow session.

    Draws the same map the camera draws — with the session's mow track shaded
    as coverage — and replaces the live "Updated HH:MM" stamp with a ribbon
    carrying the session's own numbers. Every value comes from the report
    snapshot, so the picture and the figures describe the same session even
    when the device has long since reset its counters.
    """
    renderer = MapRenderer(
        theme=theme,
        language=language,
        clean_mode=False,
        show_coverage=True,
        output_resolution=output_resolution,
    )
    stamp = finished_local.strftime("%Y-%m-%d %H:%M")
    image, _transformer = renderer.render_static(scene, map_data, stamp)
    _draw_report_ribbon(image, renderer, report, stamp)

    if output_resolution != IMAGE_WIDTH:
        image = image.resize(
            (output_resolution, output_resolution), Image.Resampling.LANCZOS
        )
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _draw_report_ribbon(
    image: Image.Image,
    renderer: MapRenderer,
    report: dict[str, Any],
    stamp: str,
) -> None:
    """Draw the session summary ribbon across the top of the map card."""
    palette = renderer._palette
    draw = ImageDraw.Draw(image, "RGBA")
    left, top, right, _bottom = MAP_RECT
    height = 92
    draw.rounded_rectangle(
        (left, top, right, top + height),
        radius=MAP_RADIUS,
        fill=palette.card_bg,
        outline=palette.card_border,
    )

    completed = report.get("outcome") == "completed"
    title = renderer._t("report_completed" if completed else "report_aborted")
    title_font = _load_font(22, bold=True)
    label_font = _load_font(13)
    value_font = _load_font(18, bold=True)

    draw.text((left + 22, top + 16), title, fill=palette.text, font=title_font)
    stamp_box = draw.textbbox((0, 0), stamp, font=label_font)
    draw.text(
        (right - 22 - int(stamp_box[2] - stamp_box[0]), top + 22),
        stamp,
        fill=palette.text_muted,
        font=label_font,
    )

    area = report.get("area_m2")
    total = report.get("total_area_m2")
    area_text = "—" if area is None else f"{area:g} m²"
    if area is not None and total:
        area_text = f"{area:g} / {total:g} m²"
    metrics = [
        (renderer._t("report_mowed"), area_text),
        (renderer._t("report_duration"), _format_duration(report.get("duration_min"))),
        (renderer._t("report_job"), _truncate(_enum_label(report.get("job_type")), 18)),
    ]
    column_width = (right - left - 44) / len(metrics)
    for index, (label, value) in enumerate(metrics):
        x = left + 22 + index * column_width
        draw.text((x, top + 48), label, fill=palette.text_muted, font=label_font)
        draw.text((x, top + 64), value, fill=palette.text, font=value_font)
