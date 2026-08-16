"""Bundled sample-bhajan presets (Phase 20).

Each preset is a small dict with lyrics + suggested project fields.
Keeps the spec's canonical Shiva bhajan reachable via one CLI/API call
so newcomers can drive the full pipeline without hunting for content.
"""

from __future__ import annotations

from typing import TypedDict


class BhajanPreset(TypedDict):
    id: str
    name: str
    deity: str
    style: str
    aspect_ratio: str
    language: str
    lyrics: str


SAMPLE_PRESETS: dict[str, BhajanPreset] = {
    "shiva-jai-shiv-shambho": {
        "id": "shiva-jai-shiv-shambho",
        "name": "Jai Shiv Shambho",
        "deity": "Shiva",
        "style": "shiva-himalayan",
        "aspect_ratio": "9:16",
        "language": "hi",
        "lyrics": (
            "जय शिव शंभो, जय महेश्वर\n"
            "आदि अनंत, तू ही ईश्वर\n"
            "तेरी कृपा से राह मिले\n"
            "हो जाए भव से पार"
        ),
    },
    "krishna-vrindavan": {
        "id": "krishna-vrindavan",
        "name": "Vrindavan Krishna",
        "deity": "Krishna",
        "style": "krishna-vrindavan",
        "aspect_ratio": "9:16",
        "language": "hi",
        "lyrics": (
            "राधे राधे, राधे राधे\n"
            "बंसी बजाओ मोहन\n"
            "यमुना किनारे नाचो श्याम\n"
            "वृंदावन के प्यारे कान्हा"
        ),
    },
    "hanuman-chalisa-opening": {
        "id": "hanuman-chalisa-opening",
        "name": "Hanuman Chalisa (opening)",
        "deity": "Hanuman",
        "style": "hanuman",
        "aspect_ratio": "9:16",
        "language": "hi",
        "lyrics": (
            "श्रीगुरु चरन सरोज रज, निज मन मुकुर सुधारि\n"
            "बरनऊँ रघुबर बिमल जसु, जो दायकु फल चारि\n"
            "जय हनुमान ज्ञान गुन सागर\n"
            "जय कपीस तिहुँ लोक उजागर"
        ),
    },
}


def get_preset(preset_id: str) -> BhajanPreset:
    try:
        return SAMPLE_PRESETS[preset_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown preset {preset_id!r}; "
            f"available: {sorted(SAMPLE_PRESETS)}"
        ) from exc
