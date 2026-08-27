"""Phase 04 adapter — load governed boundaries and Phase 03 intelligence.

The Phase 03 contract (`docs/contracts/operational-intelligence-contract.md`)
produces per-unit intelligence records on disk but stops short of the API
surface. The backend's `risks`/`alerts` domain model was deliberately left
unwired to that output. This script is the adapter that closes the gap:

    data/som_admin_boundaries.geojson.zip   ->  admin_units + boundary_revisions
    data/operational/intelligence/<track>/  ->  risk_signals

It recomputes nothing. Risk level, probability, drivers, data quality and
warning eligibility are copied from the Phase 03 records verbatim; only the
key mapping and enum translation happen here, exactly as the contract's
"Backend integration note" specifies.

Two properties matter for operating it safely:

* **Idempotent.** Every row it writes is tagged in `provenance` with
  `_loader`. A re-run deletes only its own previous rows and re-inserts, so it
  never duplicates and never touches records created by any other process.
* **Honest about scope.** Flood intelligence is station-scoped. Stations are
  not administrative units, so each flood signal is keyed to the district the
  Phase 03 record itself names in `exposure.linked_district_id`, with the
  station identity, coordinates and thresholds carried in `provenance`. The
  signal still describes the *gauge*, and the frontend renders it as such —
  it is never promoted to district-wide flood coverage.

Usage (from `backend/`):

    python -m scripts.load_operational_intelligence            # load
    python -m scripts.load_operational_intelligence --dry-run  # report only
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.enums import AlertStatus, Classification, RiskDomain, RiskLevel
from app.db.models.core import AdminUnit, Alert, BoundaryRevision, RiskSignal
from app.db.session import SessionLocal
from app.modules.geography.service import (
    BoundaryValidationError,
    parse_feature,
    validate_hierarchy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_ARCHIVE = REPO_ROOT / "data" / "som_admin_boundaries.geojson.zip"
INTELLIGENCE_ROOT = REPO_ROOT / "data" / "operational" / "intelligence"
STATION_METADATA = REPO_ROOT / "docs" / "river-station-and-boundary-metadata.md"

#: Marks every row this script owns, so a re-run can clean up after itself
#: without disturbing rows written by the development seed or by an operator.
LOADER_TAG = "phase04-operational-adapter"

BOUNDARY_VERSION = "som-ocha-adm-2024"
BOUNDARY_SOURCE = "OCHA Somalia administrative boundaries (som_admin_boundaries.geojson)"
BOUNDARY_VALID_FROM = date(2024, 1, 1)

#: Phase 03 `risk_type` -> backend `RiskDomain`. The contract's FLOOD track is
#: riverine only, so it maps to RIVER_FLOOD and never to FLASH_FLOOD.
DOMAIN_BY_TRACK = {
    "drought": RiskDomain.DROUGHT,
    "flood": RiskDomain.RIVER_FLOOD,
    "food_security": RiskDomain.FOOD_SECURITY,
}

#: Phase 03 writes SEVERE; the backend enum writes CRITICAL. Same band.
#: Codes the Phase 03 contract requires to be rejected as ungeographic. The
#: drought track carries an "Unspecified" bucket that must never be surfaced as
#: a place, even though it can hold a non-NORMAL risk level.
UNGEOGRAPHIC_CODES = {"unspecified", "unknown", "", "none", "null"}

LEVEL_MAP = {
    "NORMAL": RiskLevel.NORMAL,
    "WATCH": RiskLevel.WATCH,
    "WARNING": RiskLevel.WARNING,
    "SEVERE": RiskLevel.CRITICAL,
    "CRITICAL": RiskLevel.CRITICAL,
}


@dataclass
class LoadReport:
    admin_units: int = 0
    revisions: int = 0
    signals_by_track: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    rejected_ungeographic: int = 0
    candidate_alerts: int = 0

    def render(self) -> str:
        lines = [
            f"admin units upserted : {self.admin_units}",
            f"boundary revisions   : {self.revisions}",
        ]
        for track, count in sorted(self.signals_by_track.items()):
            lines.append(f"risk signals [{track:<13}]: {count}")
        if self.candidate_alerts:
            lines.append(
                f"candidate draft alerts: {self.candidate_alerts} "
                "(awaiting analyst review; none published)"
            )
        if self.rejected_ungeographic:
            lines.append(
                f"rejected ungeographic: {self.rejected_ungeographic} "
                "(contract requires these are never surfaced)"
            )
        if self.skipped:
            lines.append(f"skipped ({len(self.skipped)}):")
            lines.extend(f"  - {reason}" for reason in self.skipped[:20])
            if len(self.skipped) > 20:
                lines.append(f"  … and {len(self.skipped) - 20} more")
        return "\n".join(lines)


# --------------------------------------------------------------- boundaries --


def _governed_features() -> list[dict[str, Any]]:
    """Build a FeatureCollection in the shape `parse_feature` requires.

    The OCHA files carry `adm{N}_pcode`/`adm{N}_name`; the governed schema
    wants `stable_code`, `name`, `level` and an explicit `parent_code`. The
    pcodes are the same identifiers Phase 03 uses for its geography, which is
    what lets the two datasets join without a lookup table.
    """
    if not BOUNDARY_ARCHIVE.exists():
        raise SystemExit(f"Boundary archive not found: {BOUNDARY_ARCHIVE}")

    features: list[dict[str, Any]] = []
    with zipfile.ZipFile(BOUNDARY_ARCHIVE) as archive:
        levels = (
            ("som_admin0.geojson", "country", "adm0_pcode", "adm0_name", None),
            ("som_admin1.geojson", "region", "adm1_pcode", "adm1_name", "adm0_pcode"),
            ("som_admin2.geojson", "district", "adm2_pcode", "adm2_name", "adm1_pcode"),
        )
        for filename, level, code_key, name_key, parent_key in levels:
            collection = json.loads(archive.read(filename))
            for feature in collection["features"]:
                properties = feature.get("properties") or {}
                code = properties.get(code_key)
                name = properties.get(name_key)
                if not code or not name:
                    continue
                if (
                    str(code).strip().lower() in UNGEOGRAPHIC_CODES
                    or str(name).strip().lower() in UNGEOGRAPHIC_CODES
                ):
                    # The OCHA admin2 file carries a district literally named
                    # "Unspecified". It is a residual bucket, not a place, and
                    # the contract requires it is never surfaced — so it does
                    # not become an administrative unit either.
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "geometry": feature.get("geometry"),
                        "properties": {
                            "stable_code": str(code),
                            "name": str(name),
                            "level": level,
                            "parent_code": (
                                str(properties[parent_key])
                                if parent_key and properties.get(parent_key)
                                else None
                            ),
                            "aliases": [],
                        },
                    }
                )
    return features


def load_boundaries(db, report: LoadReport, *, dry_run: bool) -> dict[str, AdminUnit]:
    """Upsert administrative units and their boundary revisions.

    Validation is delegated to the same `parse_feature`/`validate_hierarchy`
    helpers the `/geography/boundaries/import` endpoint uses, so a geometry
    this script accepts is exactly one the governed API would accept.
    """
    raw = _governed_features()
    try:
        parsed = [
            parse_feature(
                feature,
                version=BOUNDARY_VERSION,
                source=BOUNDARY_SOURCE,
                valid_from=BOUNDARY_VALID_FROM,
            )
            for feature in raw
        ]
        validate_hierarchy(parsed)
    except BoundaryValidationError as exc:
        raise SystemExit(f"Boundary validation failed: {exc}") from exc

    existing = {
        unit.stable_code: unit
        for unit in db.scalars(select(AdminUnit)).all()
    }
    units: dict[str, AdminUnit] = dict(existing)

    if dry_run:
        report.admin_units = len(parsed)
        report.revisions = len(parsed)
        # Expose the codes that *would* exist so the join against the Phase 03
        # records can be validated without writing anything. A dry run that
        # cannot check the key mapping would report a false failure for every
        # record on a fresh database.
        for feature in parsed:
            units.setdefault(feature.stable_code, AdminUnit(
                stable_code=feature.stable_code,
                name=feature.name,
                level=feature.level,
                boundary_version=feature.version,
                boundary_source=feature.source,
                valid_from=feature.valid_from,
                valid_to=None,
                aliases=list(feature.aliases),
                geometry=None,
            ))
        return units

    for feature in parsed:
        unit = units.get(feature.stable_code)
        if unit is None:
            unit = AdminUnit(
                stable_code=feature.stable_code,
                name=feature.name,
                level=feature.level,
                boundary_version=feature.version,
                boundary_source=feature.source,
                valid_from=feature.valid_from,
                valid_to=None,
                aliases=list(feature.aliases),
                geometry=feature.geometry,
            )
            db.add(unit)
            units[feature.stable_code] = unit
        else:
            unit.name = feature.name
            unit.level = feature.level
            unit.boundary_version = feature.version
            unit.boundary_source = feature.source
            unit.geometry = feature.geometry
        report.admin_units += 1
    db.flush()

    # Parent links need every unit to have an id, so they are set in a second
    # pass once the flush above has assigned primary keys.
    for feature in parsed:
        unit = units[feature.stable_code]
        unit.parent_id = (
            units[feature.parent_code].id if feature.parent_code else None
        )

        revision = db.scalar(
            select(BoundaryRevision).where(
                BoundaryRevision.admin_unit_id == unit.id,
                BoundaryRevision.version == feature.version,
            )
        )
        if revision is None:
            db.add(
                BoundaryRevision(
                    admin_unit_id=unit.id,
                    parent_admin_unit_id=(
                        units[feature.parent_code].id if feature.parent_code else None
                    ),
                    version=feature.version,
                    source=feature.source,
                    valid_from=feature.valid_from,
                    valid_to=None,
                    geometry=feature.geometry,
                )
            )
            report.revisions += 1
    db.flush()
    return units


# ------------------------------------------------------------ station facts --


def _station_metadata() -> dict[str, dict[str, Any]]:
    """Parse the documented river-gauge catalogue.

    Coordinates are needed so the flood map can place a marker at the gauge.
    The source catalogue mislabels its own latitude/longitude columns; the
    documentation records the corrected order, and this reads that corrected
    table rather than re-deriving it.
    """
    stations: dict[str, dict[str, Any]] = {}
    if not STATION_METADATA.exists():
        return stations

    for line in STATION_METADATA.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| Code") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 9:
            continue
        code = cells[0]
        if not (len(code) == 5 and code[:2] in {"SH", "JB"} and code[2:].isdigit()):
            continue
        try:
            stations[code] = {
                "station_name": cells[1],
                "river_name": cells[2],
                "latitude": float(cells[3]),
                "longitude": float(cells[4]),
                "threshold_moderate_m": float(cells[5]),
                "threshold_high_m": float(cells[6]),
                "threshold_bankfull_m": float(cells[7]),
                "station_status": cells[8],
            }
        except ValueError:
            continue
    return stations


# ------------------------------------------------------------ intelligence --


def _latest_file(track: str) -> Path | None:
    directory = INTELLIGENCE_ROOT / track
    if not directory.exists():
        return None
    candidates = sorted(directory.glob("*.json"))
    return candidates[-1] if candidates else None


def _provenance(record: dict[str, Any], track: str, source_file: Path) -> dict[str, Any]:
    """Flatten the Phase 03 record into the open provenance envelope.

    Field names are chosen to match what the frontend already reads, so no UI
    change is needed for these records to render with full evidence.
    """
    model = record.get("model") or {}
    quality = record.get("data_quality") or {}
    freshness = quality.get("freshness") or {}
    warning = record.get("warning") or {}
    lineage = record.get("lineage") or {}
    impact = record.get("impact_summary") or {}
    exposure = record.get("exposure") or {}

    provenance: dict[str, Any] = {
        "_loader": LOADER_TAG,
        "_source_file": str(source_file.relative_to(REPO_ROOT)).replace("\\", "/"),
        "intelligence_id": record.get("intelligence_id"),
        "track": track,
        "model_id": model.get("id"),
        "model_version": model.get("version"),
        "algorithm": model.get("algorithm"),
        "calibration_method": model.get("calibration_method"),
        "pipeline_version": lineage.get("pipeline_version"),
        "dataset_checksum": lineage.get("dataset_checksum_sha256"),
        "data_quality": quality.get("overall_status") or quality.get("model_input_quality"),
        "feature_availability": quality.get("feature_availability"),
        "freshness": freshness.get("status"),
        "warning_status": warning.get("status"),
        "warning_eligible": warning.get("eligible"),
        "suppression_reason": warning.get("suppression_reason"),
        "reason_codes": warning.get("reason_codes") or [],
        "prediction_horizon": record.get("prediction_horizon"),
        "valid_from": record.get("valid_from"),
        "valid_until": record.get("valid_until"),
        "limitations": record.get("limitations") or [],
        "generated_at": record.get("generated_at"),
        "as_of_date": record.get("as_of_date"),
        # Exposure is carried with its own distinct labels. `population_context`
        # and `population_potentially_exposed` are never merged into a single
        # "affected" figure — the contract forbids it, and for flood the second
        # value is legitimately null.
        "population_context": exposure.get("population_context"),
        "population_potentially_exposed": exposure.get("population_potentially_exposed"),
        "exposure_method": exposure.get("exposure_method"),
        "exposure_scope_type": exposure.get("scope_type"),
    }

    # The impact summary carries the operational hydrology/agronomy phrasing
    # the domain pages render (level condition, rate of rise, antecedent wetness).
    for key, value in impact.items():
        provenance.setdefault(key, value)

    return {key: value for key, value in provenance.items() if value is not None}


def load_track(
    db,
    track: str,
    units: dict[str, AdminUnit],
    stations: dict[str, dict[str, Any]],
    report: LoadReport,
    *,
    dry_run: bool,
) -> None:
    source = _latest_file(track)
    if source is None:
        report.skipped.append(f"{track}: no intelligence files found")
        return

    records = json.loads(source.read_text(encoding="utf-8"))
    domain = DOMAIN_BY_TRACK[track]
    written = 0

    for record in records:
        geography = record.get("geography") or {}
        geography_type = geography.get("type")
        geography_id = geography.get("id")

        if geography_type == "STATION":
            # A gauge is not an administrative unit. Key the signal to the
            # district the record itself names, and carry the station identity
            # in provenance so the UI keeps presenting it as a gauge.
            exposure = record.get("exposure") or {}
            unit_code = exposure.get("linked_district_id")
        else:
            unit_code = geography_id

        if not unit_code:
            report.skipped.append(f"{track}/{geography_id}: no administrative key")
            continue

        if str(unit_code).strip().lower() in UNGEOGRAPHIC_CODES or str(
            geography.get("name", "")
        ).strip().lower() in UNGEOGRAPHIC_CODES:
            # Rejected by contract, not by accident: this bucket is not a place
            # and must never appear on a map or in a district count.
            report.rejected_ungeographic += 1
            continue

        unit = units.get(str(unit_code))
        if unit is None:
            # Never invent geography. An unmatched code is reported, not guessed.
            report.skipped.append(
                f"{track}/{geography_id}: no admin unit for code {unit_code}"
            )
            continue

        raw_level = str((record.get("prediction") or {}).get("risk_level") or "").upper()
        level = LEVEL_MAP.get(raw_level)
        if level is None:
            # UNKNOWN means the model withheld a prediction on quality grounds.
            # There is no UNKNOWN member in the backend enum, so such records
            # are skipped rather than being coerced into NORMAL, which would
            # read as "no elevated risk" and be actively misleading.
            report.skipped.append(
                f"{track}/{geography_id}: risk_level {raw_level or 'missing'} not representable"
            )
            continue

        prediction = record.get("prediction") or {}
        provenance = _provenance(record, track, source)

        if geography_type == "STATION":
            code = str(record.get("station_code") or geography_id)
            provenance["station_code"] = code
            provenance["geography_scope"] = "STATION"
            provenance["linked_district_id"] = unit_code
            provenance["linked_district_name"] = (record.get("exposure") or {}).get(
                "linked_district_name"
            )
            if record.get("river_name"):
                provenance["river_name"] = record["river_name"]
            provenance.update(stations.get(code, {}))
        else:
            provenance["geography_scope"] = geography_type

        thresholds = prediction.get("risk_thresholds")
        if thresholds:
            provenance["risk_thresholds"] = thresholds
        if prediction.get("threshold_version"):
            provenance["threshold_version"] = prediction["threshold_version"]

        target_period = (
            record.get("prediction_horizon")
            or record.get("valid_until")
            or record.get("as_of_date")
            or "unspecified"
        )

        if dry_run:
            written += 1
            continue

        generated = record.get("generated_at")
        created_at = None
        if isinstance(generated, str):
            try:
                created_at = datetime.fromisoformat(generated.replace("Z", "+00:00"))
            except ValueError:
                created_at = None

        signal = RiskSignal(
            domain=domain,
            admin_unit_id=unit.id,
            level=level,
            score=prediction.get("probability"),
            confidence=(record.get("data_quality") or {}).get("feature_availability"),
            drivers=list(record.get("drivers") or []),
            provenance=provenance,
            target_period=str(target_period)[:80],
        )
        if created_at is not None:
            signal.created_at = created_at
        db.add(signal)
        written += 1

    report.signals_by_track[track] = written


def clear_previous(db) -> tuple[int, int]:
    """Remove rows a previous run of this adapter wrote, leaving others alone.

    Alerts are deleted before their signals to satisfy the foreign key. Only
    alerts pointing at a loader-tagged signal are touched, so an operator's own
    warnings and the development seed's synthetic alert both survive a re-run.
    """
    owned = {
        signal.id: signal
        for signal in db.scalars(select(RiskSignal)).all()
        if isinstance(signal.provenance, dict)
        and signal.provenance.get("_loader") == LOADER_TAG
    }

    alerts_removed = 0
    for alert in db.scalars(select(Alert)).all():
        if alert.signal_id in owned:
            db.delete(alert)
            alerts_removed += 1
    db.flush()

    for signal in owned.values():
        db.delete(signal)
    db.flush()
    return len(owned), alerts_removed



# -------------------------------------------------------- candidate alerts --


DOMAIN_TITLE = {
    RiskDomain.DROUGHT: "Drought risk",
    RiskDomain.RIVER_FLOOD: "River flood risk",
    RiskDomain.FLASH_FLOOD: "Flash flood risk",
    RiskDomain.FOOD_SECURITY: "Food security deterioration",
}


def create_candidate_alerts(db, units: dict[str, AdminUnit], report: LoadReport) -> None:
    """Raise a DRAFT alert for every warning-eligible Phase 03 candidate.

    The contract stops at `warning.status == "CANDIDATE"` and states plainly
    that the review workflow is Phase 04's to own. A candidate therefore enters
    the queue as a **draft** — the lowest governance state — and advances only
    when a human with the right capability moves it. Nothing here approves or
    publishes anything, and the platform's `automatic_warning_publication`
    invariant remains false.
    """
    by_id = {unit.id: unit for unit in units.values()}

    for signal in db.scalars(select(RiskSignal)).all():
        provenance = signal.provenance or {}
        if not isinstance(provenance, dict) or provenance.get("_loader") != LOADER_TAG:
            continue
        if not provenance.get("warning_eligible"):
            continue

        unit = by_id.get(signal.admin_unit_id)
        place = provenance.get("station_code") or (unit.name if unit else "Unnamed area")
        headline = DOMAIN_TITLE.get(signal.domain, "Risk")

        reasons = provenance.get("reason_codes") or []
        reason_text = (
            "Reason codes: " + ", ".join(str(code) for code in reasons)
            if reasons
            else "No reason codes were attached to this candidate."
        )
        probability = (
            f"{round(signal.score * 100)}%" if isinstance(signal.score, (int, float)) else "withheld"
        )

        summary = (
            f"Model-generated candidate from the {provenance.get('track')} track. "
            f"Modelled probability {probability} over {provenance.get('prediction_horizon', 'the forecast window')}. "
            f"{reason_text} "
            f"Data quality {provenance.get('data_quality', 'not reported')}. "
            "This candidate has not been reviewed or approved."
        )

        db.add(
            Alert(
                signal_id=signal.id,
                status=AlertStatus.DRAFT,
                classification=Classification.INTERNAL,
                title=f"{headline} — {place}",
                summary=summary,
            )
        )
        report.candidate_alerts += 1
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be loaded without writing anything.",
    )
    parser.add_argument(
        "--create-candidate-alerts",
        action="store_true",
        help=(
            "Raise a DRAFT alert for every warning-eligible candidate so the "
            "review queue is populated. Nothing is approved or published."
        ),
    )
    parser.add_argument(
        "--skip-boundaries",
        action="store_true",
        help="Load intelligence only, assuming boundaries are already present.",
    )
    args = parser.parse_args()

    report = LoadReport()
    stations = _station_metadata()

    with SessionLocal() as db:
        if args.skip_boundaries:
            units = {unit.stable_code: unit for unit in db.scalars(select(AdminUnit)).all()}
        else:
            units = load_boundaries(db, report, dry_run=args.dry_run)

        removed, alerts_removed = (0, 0) if args.dry_run else clear_previous(db)

        for track in DOMAIN_BY_TRACK:
            load_track(db, track, units, stations, report, dry_run=args.dry_run)

        if args.create_candidate_alerts and not args.dry_run:
            db.flush()
            create_candidate_alerts(db, units, report)

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(f"Phase 04 operational adapter — {'DRY RUN' if args.dry_run else 'LOADED'}")
    print(f"generated at         : {datetime.now(timezone.utc).isoformat()}")
    print(f"stations catalogued  : {len(stations)}")
    if not args.dry_run:
        print(f"previous rows removed: {removed} signals, {alerts_removed} alerts")
    print(report.render())


if __name__ == "__main__":
    main()
