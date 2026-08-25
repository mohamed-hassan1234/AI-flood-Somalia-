from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import Classification, RiskLevel
from app.db.models.core import (
    AuditEvent,
    DatasetSnapshot,
    FeatureVersion,
    ModelVersion,
    Prediction,
)
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    grants_for,
    require_access,
)
from app.modules.ml_registry.schemas import (
    FeatureVersionCreate,
    FeatureVersionResponse,
    ModelOperationsResponse,
    ModelTransition,
    ModelVersionCreate,
    ModelVersionResponse,
    PredictionCreate,
    PredictionResponse,
    SnapshotCreate,
    SnapshotOptionResponse,
    SnapshotResponse,
)
from app.modules.ml_registry.service import transition_model

router = APIRouter(prefix="/ml", tags=["ML governance"])


@router.get("/snapshot-options", response_model=list[SnapshotOptionResponse])
def list_snapshot_options(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DatasetSnapshot]:
    if not ({"scenarios.run", "models.read"} & principal.capabilities):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing model or scenario read capability")
    return list(db.scalars(select(DatasetSnapshot).order_by(DatasetSnapshot.name)).all())


@router.get("/operations", response_model=list[ModelOperationsResponse])
def list_model_operations(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ModelOperationsResponse]:
    grants_for(principal, "models.read")
    rows = db.execute(
        select(ModelVersion, DatasetSnapshot, FeatureVersion)
        .join(DatasetSnapshot, DatasetSnapshot.id == ModelVersion.dataset_snapshot_id)
        .join(FeatureVersion, FeatureVersion.id == ModelVersion.feature_version_id)
        .order_by(ModelVersion.created_at.desc())
    ).all()
    required_card_fields = {
        "chronological_backtest",
        "region_evaluation",
        "season_evaluation",
        "limitations",
    }
    return [
        ModelOperationsResponse(
            id=model.id,
            name=model.name,
            version=model.version,
            state=model.state,
            snapshot_name=snapshot.name,
            snapshot_row_count=snapshot.row_count,
            feature_name=feature.name,
            feature_version=feature.version,
            metrics=model.metrics,
            model_card=model.model_card,
            promotion_ready=required_card_fields.issubset(model.model_card)
            and bool(model.metrics),
        )
        for model, snapshot, feature in rows
    ]


@router.post("/snapshots", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
def register_snapshot(
    body: SnapshotCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetSnapshot:
    grants_for(principal, "models.train")
    if db.scalar(
        select(DatasetSnapshot.id).where(DatasetSnapshot.content_hash == body.content_hash)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dataset snapshot already registered")
    snapshot = DatasetSnapshot(**body.model_dump())
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.post(
    "/feature-versions", response_model=FeatureVersionResponse, status_code=status.HTTP_201_CREATED
)
def register_features(
    body: FeatureVersionCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> FeatureVersion:
    grants_for(principal, "models.train")
    feature = FeatureVersion(**body.model_dump())
    db.add(feature)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Feature version already exists") from exc
    db.refresh(feature)
    return feature


@router.post("/models", response_model=ModelVersionResponse, status_code=status.HTTP_201_CREATED)
def register_model(
    body: ModelVersionCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ModelVersion:
    grants_for(principal, "models.train")
    if (
        db.get(DatasetSnapshot, body.dataset_snapshot_id) is None
        or db.get(FeatureVersion, body.feature_version_id) is None
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Snapshot or feature version does not exist"
        )
    model = ModelVersion(**body.model_dump(), state="candidate")
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


@router.post("/models/{model_id}/transitions", response_model=ModelVersionResponse)
def transition_registry_model(
    model_id: UUID,
    body: ModelTransition,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ModelVersion:
    model = db.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model version not found")
    capability = (
        "models.rollback"
        if model.state == "production" and body.target == "validated"
        else "models.promote"
    )
    grants_for(principal, capability)
    try:
        target = transition_model(model.state, body.target, model.metrics, model.model_card)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if target == "production":
        current = db.scalars(
            select(ModelVersion).where(
                ModelVersion.name == model.name,
                ModelVersion.state == "production",
                ModelVersion.id != model.id,
            )
        ).all()
        for champion in current:
            champion.state = "validated"
    model.state = target
    db.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            actor_id=principal.user_id,
            action=capability,
            entity_type="model_version",
            entity_id=model.id,
            details={"state": target},
        )
    )
    db.commit()
    db.refresh(model)
    return model


@router.post("/predictions", response_model=PredictionResponse, status_code=status.HTTP_201_CREATED)
def register_prediction(
    body: PredictionCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Prediction:
    require_access(principal, "models.infer", Classification.INTERNAL, body.admin_unit_id)
    model = db.get(ModelVersion, body.model_version_id)
    if model is None or model.state != "production":
        raise HTTPException(status.HTTP_409_CONFLICT, "Inference requires a production model")
    level = (
        RiskLevel.CRITICAL
        if body.probability >= 0.8
        else RiskLevel.WARNING
        if body.probability >= 0.6
        else RiskLevel.WATCH
        if body.probability >= 0.4
        else RiskLevel.NORMAL
    )
    prediction = Prediction(
        **body.model_dump(),
        level=level,
        dataset_snapshot_id=model.dataset_snapshot_id,
        feature_version_id=model.feature_version_id,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction
