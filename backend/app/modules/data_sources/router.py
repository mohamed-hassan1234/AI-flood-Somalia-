from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models.core import DataSource, IngestionRun
from app.db.session import get_db
from app.integrations.storage.port import ObjectStorage
from app.integrations.storage.s3 import S3ObjectStorage
from app.modules.auth.dependencies import Principal, get_current_principal, grants_for
from app.modules.data_sources.health import assess_health
from app.modules.data_sources.schemas import (
    DataSourceCreate,
    DataSourceHealthResponse,
    DataSourceResponse,
)
from app.modules.ingestion.object_storage_provider import ObjectStorageCsvProvider
from app.modules.ingestion.schemas import IngestionRunResponse, ObjectStorageImportRequest
from app.modules.ingestion.service import import_provider, import_small_csv

router = APIRouter(prefix="/data-sources", tags=["data sources"])
MAX_INLINE_CSV_BYTES = 256 * 1024


def get_object_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ObjectStorage:
    return S3ObjectStorage(settings)


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    body: DataSourceCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> DataSource:
    grants_for(principal, "data_sources.manage")
    if db.scalar(select(DataSource).where(DataSource.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Data source name already exists")
    source = DataSource(**body.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("", response_model=list[DataSourceResponse])
def list_sources(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DataSource]:
    grants_for(principal, "data_sources.read")
    return list(db.scalars(select(DataSource).order_by(DataSource.name)).all())


@router.get("/{source_id}/health", response_model=DataSourceHealthResponse)
def source_health(
    source_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> DataSourceHealthResponse:
    grants_for(principal, "data_sources.read")
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found")
    run = db.scalar(
        select(IngestionRun)
        .where(IngestionRun.source_id == source.id)
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )
    last_success = run.finished_at if run and run.status == "succeeded" else None
    expected = timedelta(minutes=source.expected_frequency_minutes or 1440)
    health = assess_health(
        datetime.now(timezone.utc),
        last_success,
        expected,
        bool(run and run.status == "failed"),
        None,
        run.rows_quarantined if run else 0,
    )
    return DataSourceHealthResponse(
        source_id=source.id,
        status=health.status,
        last_success=last_success,
        last_run_status=run.status if run else None,
        rows_received=run.rows_received if run else 0,
        rows_quarantined=run.rows_quarantined if run else 0,
    )


@router.post(
    "/{source_id}/imports/csv",
    response_model=IngestionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_csv(
    source_id: UUID,
    file: UploadFile,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> IngestionRun:
    grants_for(principal, "data_sources.manage")
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found")
    if source.access_method not in {"file", "manual", "object_storage"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Source is not configured for file fallback")
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only CSV uploads are accepted")
    payload = await file.read(MAX_INLINE_CSV_BYTES + 1)
    if len(payload) > MAX_INLINE_CSV_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "Inline CSV exceeds 256 KiB; submit it through object storage for asynchronous processing",
        )
    try:
        content = payload.decode("utf-8-sig")
        return import_small_csv(db, source, content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post(
    "/{source_id}/imports/object-storage",
    response_model=IngestionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_object_storage(
    source_id: UUID,
    body: ObjectStorageImportRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> IngestionRun:
    grants_for(principal, "data_sources.manage")
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found")
    if source.access_method != "object_storage" or not source.verified or not source.enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Connector ingestion requires an enabled, verified object-storage source",
        )
    expected_prefix = f"sources/{source.id}/"
    if not body.object_key.startswith(expected_prefix):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Object key is outside source prefix")
    try:
        provider = ObjectStorageCsvProvider(storage, body.object_key, body.sha256)
        return import_provider(db, source, provider)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
