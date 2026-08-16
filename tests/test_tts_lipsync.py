"""TTS + lip-sync adapter smoke tests."""

from __future__ import annotations

import asyncio
import os

import pytest

from models.lipsync import get_lipsync_engine
from models.lipsync.base import LipSyncRequest
from models.tts import get_tts_engine
from models.tts.base import TTSRequest


def test_noop_lipsync_returns_input_unchanged(tmp_path):
    engine = get_lipsync_engine()
    assert engine.name == "noop"  # default in test env
    v = tmp_path / "fake.mp4"
    v.write_bytes(b"x")
    a = tmp_path / "fake.wav"
    a.write_bytes(b"y")

    async def run():
        res = await engine.synchronize(
            LipSyncRequest(video_path=v, audio_path=a)
        )
        assert res.path == v
        assert res.engine == "noop"

    asyncio.run(run())


def test_stub_tts_engine_refuses_to_generate():
    engine = get_tts_engine()
    assert engine.name == "stub"  # default in test env

    async def run():
        with pytest.raises(NotImplementedError):
            await engine.generate(TTSRequest(text="जय शिव शंभो", language="hi"))

    asyncio.run(run())


@pytest.mark.skipif(
    os.environ.get("RUN_PIPER_INTEGRATION") != "1",
    reason="Set RUN_PIPER_INTEGRATION=1 and PIPER_VOICES_DIR (with a voice) to run.",
)
def test_piper_engine_real_synth(tmp_path):
    os.environ["TTS_ENGINE"] = "piper"
    from backend.app.core.settings import get_settings
    from models.tts import reset_tts_engine_cache

    get_settings.cache_clear()
    reset_tts_engine_cache()

    engine = get_tts_engine()
    assert engine.name == "piper"

    async def run():
        res = await engine.generate(
            TTSRequest(text="जय शिव शंभो", language="hi")
        )
        assert res.path.exists()
        assert res.sample_rate > 0

    asyncio.run(run())


@pytest.mark.skipif(
    os.environ.get("RUN_WAV2LIP_INTEGRATION") != "1",
    reason="Set RUN_WAV2LIP_INTEGRATION=1 and WAV2LIP_ROOT.",
)
def test_wav2lip_engine_real_sync(tmp_path):
    os.environ["LIPSYNC_ENGINE"] = "wav2lip"
    from backend.app.core.settings import get_settings
    from models.lipsync import reset_lipsync_engine_cache

    get_settings.cache_clear()
    reset_lipsync_engine_cache()

    engine = get_lipsync_engine()
    assert engine.name == "wav2lip"
    # Only asserting the module wires up; a real run requires a face MP4
    # and matching audio, which the user provides.
