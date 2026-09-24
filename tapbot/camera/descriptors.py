"""Serializable camera source descriptors."""

from __future__ import annotations

from dataclasses import dataclass, field

from tapbot.camera.source import CameraMetadata, CameraSourceType


@dataclass(frozen=True, slots=True)
class CameraSourceDescriptor:
    """A camera source advertised without exposing its implementation."""

    id: str
    name: str
    type: CameraSourceType
    available: bool
    metadata: CameraMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "available": self.available,
            "metadata": dict(self.metadata),
        }
