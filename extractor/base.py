from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SupplierConfig:
    name: str
    base_url: str
    endpoints: dict[str, str]


class SupplierExtractor(ABC):
    def __init__(self, config: SupplierConfig, bucket: str):
        self.config = config
        self.bucket = bucket

    @abstractmethod
    def run(self, date: str) -> None:
        """Extract all data feeds for this supplier and upload to S3."""
        ...
