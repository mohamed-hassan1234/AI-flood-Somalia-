from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DataStage
from app.db.models.core import (
    AdminUnit,
    DataSource,
    IndicatorDefinition,
    IngestionRun,
    Observation,
    QuarantineRecord,
)
from app.modules.ingestion.csv_adapter import ImportResult, parse_observation_csv
from app.modules.ingestion.ports import ObservationProvider


def import_small_csv(db: Session, source: DataSource, content: str) -> IngestionRun:
    """Import a bounded fallback file; large files are delegated to Celery."""
    return import_observation_batch(db, source, parse_observation_csv(content))


def import_provider(db: Session, source: DataSource, provider: ObservationProvider) -> IngestionRun:
    return import_observation_batch(db, source, provider.fetch())


def import_observation_batch(
    db: Session, source: DataSource, parsed: ImportResult
) -> IngestionRun:
    now = datetime.now(timezone.utc)
    run = IngestionRun(
        source_id=source.id,
        status="running",
        started_at=now,
        rows_received=len(parsed.accepted) + len(parsed.rejected),
    )
    db.add(run)
    db.flush()
    definitions = {
        definition.code: definition
        for definition in db.scalars(
            select(IndicatorDefinition).where(
                IndicatorDefinition.code.in_({item.indicator_code for item in parsed.accepted})
            )
        ).all()
    }
    for rejected in parsed.rejected:
        db.add(
            QuarantineRecord(
                ingestion_run_id=run.id,
                source_row=rejected.row_number,
                reason_code=rejected.reason,
                safe_payload={},
            )
        )
        run.rows_quarantined += 1
    for item in parsed.accepted:
        definition = definitions.get(item.indicator_code)
        if definition is None and source.verified:
            db.add(
                QuarantineRecord(
                    ingestion_run_id=run.id,
                    source_row=0,
                    reason_code="unregistered_indicator_code",
                    safe_payload={"source_record_id": item.source_record_id},
                )
            )
            run.rows_quarantined += 1
            continue
        if definition is not None and definition.unit != item.unit:
            db.add(
                QuarantineRecord(
                    ingestion_run_id=run.id,
                    source_row=0,
                    reason_code="indicator_unit_mismatch",
                    safe_payload={"source_record_id": item.source_record_id},
                )
            )
            run.rows_quarantined += 1
            continue
        if definition is not None and item.value is not None and (
            (definition.minimum_value is not None and item.value < definition.minimum_value)
            or (definition.maximum_value is not None and item.value > definition.maximum_value)
        ):
            db.add(
                QuarantineRecord(
                    ingestion_run_id=run.id,
                    source_row=0,
                    reason_code="indicator_value_out_of_range",
                    safe_payload={"source_record_id": item.source_record_id},
                )
            )
            run.rows_quarantined += 1
            continue
        unit = db.scalar(select(AdminUnit).where(AdminUnit.stable_code == item.admin_unit_code))
        if unit is None:
            db.add(
                QuarantineRecord(
                    ingestion_run_id=run.id,
                    source_row=0,
                    reason_code="unknown_admin_unit_code",
                    safe_payload={"source_record_id": item.source_record_id},
                )
            )
            run.rows_quarantined += 1
            continue
        duplicate = db.scalar(
            select(Observation.id).where(
                Observation.source_id == source.id,
                Observation.source_record_id == item.source_record_id,
            )
        )
        if duplicate is not None:
            continue
        db.add(
            Observation(
                source_id=source.id,
                source_record_id=item.source_record_id,
                admin_unit_id=unit.id,
                indicator_code=item.indicator_code,
                indicator_definition_id=definition.id if definition else None,
                value=item.value,
                value_kind="observed",
                unit=item.unit,
                reference_time=item.reference_time,
                retrieved_at=now,
                stage=DataStage.NORMALIZED if source.verified else DataStage.RAW,
                quality_flags=(
                    []
                    if source.verified
                    else [
                        "source_unverified",
                        *(["indicator_unregistered"] if definition is None else []),
                    ]
                ),
                boundary_version=unit.boundary_version,
            )
        )
        run.rows_accepted += 1
    run.status = "succeeded"
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
