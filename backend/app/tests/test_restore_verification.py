from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from scripts.verify_restore import verify_restore


def make_database(path: Path, rows: int) -> str:
    url = f"sqlite+pysqlite:///{path.as_posix()}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('synthetic-head')"))
        connection.execute(text("CREATE TABLE evidence (id INTEGER PRIMARY KEY, label VARCHAR(50))"))
        for index in range(rows):
            connection.execute(
                text("INSERT INTO evidence (id, label) VALUES (:id, :label)"),
                {"id": index + 1, "label": "SYNTHETIC / DEVELOPMENT DATA"},
            )
    engine.dispose()
    return url


def test_restore_verifier_compares_head_schema_and_counts(tmp_path: Path) -> None:
    source = create_engine(make_database(tmp_path / "source.db", 2))
    restored = create_engine(make_database(tmp_path / "restored.db", 2))
    result = verify_restore(source, restored)
    assert result.migration_head == "synthetic-head"
    assert result.table_counts["evidence"] == 2
    source.dispose()
    restored.dispose()


def test_restore_verifier_rejects_count_mismatch(tmp_path: Path) -> None:
    source = create_engine(make_database(tmp_path / "source.db", 2))
    restored = create_engine(make_database(tmp_path / "restored.db", 1))
    with pytest.raises(RuntimeError, match="count_mismatches"):
        verify_restore(source, restored)
    source.dispose()
    restored.dispose()
