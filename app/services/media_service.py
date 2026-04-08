from pathlib import Path

from app.core.config import settings


class MediaService:
    """Manages project-local storage paths while remaining cloud-storage friendly."""

    def __init__(self) -> None:
        self.base_path = Path(settings.local_storage_path)

    def build_local_path(self, *parts: str) -> Path:
        return self.base_path.joinpath(*parts)
