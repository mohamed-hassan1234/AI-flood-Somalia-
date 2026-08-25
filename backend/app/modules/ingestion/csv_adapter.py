import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO


@dataclass(frozen=True)
class ParsedObservation:
    source_record_id: str
    admin_unit_code: str
    indicator_code: str
    value: float | None
    unit: str
    reference_time: datetime


@dataclass(frozen=True)
class RejectedRow:
    row_number: int
    reason: str


@dataclass(frozen=True)
class ImportResult:
    accepted: tuple[ParsedObservation, ...]
    rejected: tuple[RejectedRow, ...]


REQUIRED_COLUMNS = {
    "source_record_id",
    "admin_unit_code",
    "indicator_code",
    "value",
    "unit",
    "reference_time",
}


def parse_observation_csv(content: str) -> ImportResult:
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
        raise ValueError("CSV does not contain the required observation columns")
    accepted: list[ParsedObservation] = []
    rejected: list[RejectedRow] = []
    seen: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        try:
            record_id = row["source_record_id"].strip()
            if not record_id or record_id in seen:
                raise ValueError("duplicate_or_missing_source_record_id")
            seen.add(record_id)
            raw_value = row["value"].strip()
            value = None if raw_value == "" else float(raw_value)
            accepted.append(
                ParsedObservation(
                    record_id,
                    row["admin_unit_code"].strip(),
                    row["indicator_code"].strip(),
                    value,
                    row["unit"].strip(),
                    datetime.fromisoformat(row["reference_time"].replace("Z", "+00:00")),
                )
            )
        except (KeyError, ValueError) as exc:
            rejected.append(RejectedRow(row_number, str(exc)))
    return ImportResult(tuple(accepted), tuple(rejected))
