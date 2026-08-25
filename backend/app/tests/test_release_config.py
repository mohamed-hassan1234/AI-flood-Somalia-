from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]


def test_compose_gates_services_on_migrations_and_seed_is_opt_in() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["backend"]["depends_on"]["migration"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["worker"]["depends_on"]["migration"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["scheduler"]["depends_on"]["migration"]["condition"] == (
        "service_completed_successfully"
    )
    assert "celery_app beat" in services["scheduler"]["command"]
    assert services["seed"]["profiles"] == ["seed"]
    assert services["seed"]["command"] == "python -m scripts.seed_development"
    assert "healthcheck" in services["backend"]
    assert "healthcheck" in services["frontend"]


def test_frontend_container_has_spa_fallback() -> None:
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "try_files $uri $uri/ /index.html;" in nginx


def test_ci_exercises_mysql_dump_restore_and_inventory_verification() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["synthetic-restore"]
    assert job["services"]["mysql"]["image"] == "mysql:8.4"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "alembic upgrade head" in commands
    assert "mysqldump" in commands
    assert "somalia_ai_restore" in commands
    assert "scripts.verify_restore" in commands


def test_ci_runs_bounded_synthetic_http_database_benchmark() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    commands = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["backend"]["steps"]
    )
    assert "scripts.benchmark_http" in commands
    assert "--max-p95-ms" in commands
    assert "--max-error-rate 0" in commands
