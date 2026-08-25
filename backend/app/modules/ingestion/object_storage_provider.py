from hashlib import sha256

from app.integrations.storage.port import ObjectStorage
from app.modules.ingestion.csv_adapter import ImportResult, parse_observation_csv


class ObjectStorageCsvProvider:
    def __init__(
        self,
        storage: ObjectStorage,
        object_key: str,
        expected_sha256: str,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.storage = storage
        self.object_key = object_key
        self.expected_sha256 = expected_sha256
        self.max_bytes = max_bytes

    def fetch(self) -> ImportResult:
        stream = self.storage.open(self.object_key)
        try:
            payload = stream.read(self.max_bytes + 1)
        finally:
            stream.close()
        if len(payload) > self.max_bytes:
            raise ValueError("Connector object exceeds the 10 MiB ingestion limit")
        if sha256(payload).hexdigest() != self.expected_sha256:
            raise ValueError("Connector object checksum does not match")
        try:
            return parse_observation_csv(payload.decode("utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise ValueError("Connector object is not valid UTF-8 CSV") from exc
