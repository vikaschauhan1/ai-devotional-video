"""Model adapter interfaces.

Every heavy ML component in this project sits behind one of the abstract
base classes exported here. Concrete implementations live under
``models/<kind>/`` and are selected at runtime through configuration
(see ``.env`` and ``backend/app/core/settings.py``).
"""

from models.image.base import ImageGenerationEngine
from models.lipsync.base import LipSyncEngine
from models.llm.base import LLMEngine
from models.tts.base import SingingGenerationEngine, TTSEngine
from models.video.base import VideoGenerationEngine

__all__ = [
    "LLMEngine",
    "ImageGenerationEngine",
    "VideoGenerationEngine",
    "LipSyncEngine",
    "TTSEngine",
    "SingingGenerationEngine",
]
