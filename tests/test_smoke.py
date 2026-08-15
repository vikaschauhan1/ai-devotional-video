"""Phase 2 smoke test: adapter interfaces import and are abstract."""

from models import (
    ImageGenerationEngine,
    LipSyncEngine,
    LLMEngine,
    SingingGenerationEngine,
    TTSEngine,
    VideoGenerationEngine,
)


def test_adapters_are_abstract():
    for cls in (
        LLMEngine,
        ImageGenerationEngine,
        VideoGenerationEngine,
        LipSyncEngine,
        TTSEngine,
        SingingGenerationEngine,
    ):
        # Instantiating an abstract base must fail.
        try:
            cls()  # type: ignore[abstract]
        except TypeError:
            continue
        raise AssertionError(f"{cls.__name__} is not abstract")
