import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotManifest:
    content_hash: str
    target_definition: dict[str, object]
    source_versions: tuple[dict[str, object], ...]
    row_count: int


def build_manifest(
    rows: list[dict[str, object]],
    target_definition: dict[str, object],
    source_versions: list[dict[str, object]],
) -> SnapshotManifest:
    canonical = json.dumps(
        {"rows": rows, "target": target_definition, "sources": source_versions},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return SnapshotManifest(
        hashlib.sha256(canonical.encode()).hexdigest(),
        target_definition,
        tuple(source_versions),
        len(rows),
    )
