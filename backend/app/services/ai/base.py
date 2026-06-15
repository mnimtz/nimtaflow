from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from PIL import Image


@dataclass
class DetectedFace:
    bbox_x: float  # relative 0.0–1.0
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: float
    embedding: Optional[List[float]] = None


@dataclass
class AIResult:
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    faces: List[DetectedFace] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    provider: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> str:
        ...

    @abstractmethod
    async def generate_tags(self, image: Image.Image, language: str = "de") -> List[str]:
        ...

    @abstractmethod
    async def detect_faces(self, image: Image.Image) -> List[DetectedFace]:
        ...

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        ...

    async def is_available(self) -> bool:
        return True
