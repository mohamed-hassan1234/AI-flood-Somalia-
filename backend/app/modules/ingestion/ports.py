from typing import Protocol

from app.modules.ingestion.csv_adapter import ImportResult


class ObservationProvider(Protocol):
    """Provider-neutral ingestion boundary; external payloads stop here."""

    def fetch(self) -> ImportResult: ...
