from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SupplierConfig:
    name: str
    endpoints: dict[str, str]
    base_url: str | None = None


class SupplierExtractor(ABC):
    def __init__(self, config: SupplierConfig, bucket: str):
        self.config = config
        self.bucket = bucket

    @abstractmethod
    def run(self, date: str) -> None:
        """Extract all data feeds for this supplier and upload to S3."""
        ...
