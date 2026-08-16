"""Placeholder image-generation engine.

Renders a real PNG containing a mood-tinted gradient background and
the scene prompt as burned-in text. This is a **real, honest** engine —
not a mock. It produces actual images that flow through the rest of
the pipeline (Ken-Burns → FFmpeg → MP4), so end-to-end works today on
a laptop with no GPU.

When a real diffusion adapter (SDXL-Turbo via OpenVINO, diffusers CPU,
Wan, etc.) is added, it drops in behind the same ``ImageGenerationEngine``
interface and this file stays untouched.
"""

from __future__ import annotations

import hashlib
import logging
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from models.image.base import (
    ImageGenerationEngine,
    ImageGenerationRequest,
    ImageGenerationResult,
)

log = logging.getLogger(__name__)


# Mood-tinted gradient endpoints (top → bottom RGB pairs).
_MOOD_GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "devotional":   ((190, 84, 20),   (46, 12, 4)),      # ember → dark
    "serene":       ((66, 106, 130),  (14, 24, 40)),     # cool blue → night
    "meditative":   ((45, 68, 120),   (12, 12, 40)),     # deep blue → indigo
    "cosmic":       ((88, 44, 140),   (10, 6, 30)),      # violet → space
    "regal":        ((178, 96, 22),   (60, 20, 8)),      # bronze → dark
    "playful":      ((240, 174, 60),  (110, 68, 20)),    # gold → warm brown
    "warm":         ((210, 120, 50),  (68, 26, 10)),
    "joyous":       ((240, 174, 60),  (150, 60, 20)),
    "epic":         ((70, 90, 160),   (14, 18, 44)),
    "sacred":       ((196, 128, 44),  (48, 16, 8)),
    "reverent":     ((160, 102, 34),  (40, 16, 6)),
    "solemn":       ((60, 66, 82),    (14, 18, 26)),
    "powerful":     ((140, 40, 30),   (30, 10, 10)),
    "transcendent": ((110, 74, 160),  (12, 10, 32)),
    "energetic":    ((220, 90, 40),   (90, 20, 12)),
    "still":        ((70, 90, 110),   (18, 24, 34)),
    "luminous":     ((220, 180, 90),  (90, 60, 20)),
    "flowing":      ((80, 130, 150),  (12, 26, 40)),
    "contemplative": ((80, 100, 140), (16, 22, 38)),
    "refined":      ((150, 120, 90),  (30, 26, 20)),
    "decorative":   ((190, 130, 60),  (60, 30, 10)),
    "sublime":      ((160, 140, 190), (30, 20, 50)),
}
_DEFAULT_GRADIENT = ((160, 96, 40), (32, 16, 8))


def _resolve_dimensions(request: ImageGenerationRequest) -> tuple[int, int]:
    """Prefer the caller's width/height; fall back to a 9:16 default."""
    w = int(request.width) if request.width else 720
    h = int(request.height) if request.height else 1280
    # Sanity clamp so ridiculous values from a hallucinated LLM don't OOM.
    w = max(64, min(w, 4096))
    h = max(64, min(h, 4096))
    return w, h


def _resolve_gradient(
    extras: dict,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    mood = str(extras.get("mood", "")).lower().strip()
    for token in mood.split():
        if token in _MOOD_GRADIENTS:
            return _MOOD_GRADIENTS[token]
    return _MOOD_GRADIENTS.get(mood, _DEFAULT_GRADIENT)


def _seed_from(request: ImageGenerationRequest) -> int:
    if request.seed is not None:
        return int(request.seed) & 0xFFFFFFFF
    h = hashlib.sha256(request.prompt.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


def _linear_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    """Vertical gradient. Draws a 1-pixel-wide strip then resizes — O(h),
    not O(w*h)."""
    w, h = size
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    if px is None:  # pragma: no cover - PIL always returns a load()
        return strip.resize(size, resample=Image.Resampling.BILINEAR)
    for y in range(h):
        t = y / max(h - 1, 1)
        px[0, y] = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
    return strip.resize(size, resample=Image.Resampling.BILINEAR)


def _add_grain(img: Image.Image, seed: int, intensity: int = 8) -> Image.Image:
    """Sprinkle deterministic film-grain-ish noise for texture.

    We sample a small noise tile and enlarge with bilinear filtering
    instead of writing every pixel from Python — same visual effect,
    ~1000x faster on large canvases.
    """
    rng = random.Random(seed)
    tile_size = 128
    noise = Image.new("L", (tile_size, tile_size))
    npx = noise.load()
    if npx is None:  # pragma: no cover
        return img
    for y in range(tile_size):
        for x in range(tile_size):
            npx[x, y] = 128 + rng.randint(-intensity, intensity)
    noise = noise.resize(img.size, resample=Image.Resampling.BILINEAR)
    noise = noise.filter(ImageFilter.GaussianBlur(radius=0.8))
    return Image.blend(img, Image.merge("RGB", (noise, noise, noise)), 0.08)


def _load_font(size: int) -> ImageFont.ImageFont:
    """Try common fonts that ship with Ubuntu; fall back to PIL default."""
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_text(
    img: Image.Image,
    *,
    scene_id: str,
    prompt: str,
    preset: str,
) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    # top-left: scene id
    title_font = _load_font(max(32, w // 16))
    draw.text((32, 32), scene_id, font=title_font, fill=(255, 255, 255, 220))

    # bottom: style preset in small
    caption_font = _load_font(max(18, w // 40))
    draw.text(
        (32, h - 32 - caption_font.size),
        preset,
        font=caption_font,
        fill=(255, 255, 255, 180),
    )

    # centre: wrapped prompt in a semi-transparent rounded panel
    body_font = _load_font(max(22, w // 34))
    # Wrap by rough character width
    chars_per_line = max(20, w // (body_font.size // 2 + 6))
    wrapped = textwrap.wrap(prompt.strip(), width=chars_per_line)
    if len(wrapped) > 8:
        wrapped = wrapped[:8]
        wrapped[-1] = wrapped[-1] + " …"

    line_h = body_font.size + 8
    total_h = line_h * len(wrapped)
    panel_pad = 24
    panel_w = w - 96
    panel_h = total_h + panel_pad * 2
    panel_x = (w - panel_w) // 2
    panel_y = (h - panel_h) // 2
    draw.rounded_rectangle(
        (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
        radius=18,
        fill=(0, 0, 0, 140),
    )

    y = panel_y + panel_pad
    for line in wrapped:
        line_w = draw.textlength(line, font=body_font)
        x = (w - int(line_w)) // 2
        draw.text((x, y), line, font=body_font, fill=(255, 255, 255, 240))
        y += line_h


class PlaceholderImageEngine(ImageGenerationEngine):
    name = "placeholder"

    def __init__(self, *, storage_root: Path) -> None:
        self.storage_root = Path(storage_root)

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResult:
        w, h = _resolve_dimensions(request)
        top, bottom = _resolve_gradient(request.extras)
        seed = _seed_from(request)
        log.info(
            "placeholder image seed=%d size=%dx%d mood=%s",
            seed,
            w,
            h,
            request.extras.get("mood", ""),
        )

        img = _linear_gradient((w, h), top, bottom)
        img = _add_grain(img, seed)
        _draw_text(
            img,
            scene_id=str(request.extras.get("scene_id", "Scene")),
            prompt=request.prompt,
            preset=str(request.extras.get("style_preset", "")),
        )

        dest_dir = (
            self.storage_root
            / "generated_images"
            / str(request.extras.get("project_id", "misc"))
        ).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Filename embeds scene_id if provided, always ends in a unique hex.
        stem = str(request.extras.get("scene_id") or "scene")
        dest = dest_dir / f"{stem}-{seed:08x}.png"
        img.save(dest, format="PNG", optimize=True)

        return ImageGenerationResult(
            path=dest,
            seed=seed,
            engine=self.name,
            metadata={
                "width": w,
                "height": h,
                "prompt": request.prompt,
                "mood": request.extras.get("mood"),
                "style_preset": request.extras.get("style_preset"),
            },
        )
