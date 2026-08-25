import argparse
from dataclasses import dataclass

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class DatabaseInventory:
    migration_head: str
    table_counts: dict[str, int]


def inventory(engine: Engine) -> DatabaseInventory:
    inspector = inspect(engine)
    tables = sorted(name for name in inspector.get_table_names() if not name.startswith("sqlite_"))
    metadata = MetaData()
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for name in tables:
            table = Table(name, metadata, autoload_with=connection)
            counts[name] = int(connection.scalar(select(func.count()).select_from(table)) or 0)
        if "alembic_version" not in tables:
            raise RuntimeError("Database has no Alembic version table")
        version = Table("alembic_version", metadata, autoload_with=connection)
        head = connection.scalar(select(version.c.version_num))
    if not isinstance(head, str) or not head:
        raise RuntimeError("Database has no migration head")
    return DatabaseInventory(head, counts)


def verify_restore(source: Engine, restored: Engine) -> DatabaseInventory:
    expected = inventory(source)
    actual = inventory(restored)
    if expected != actual:
        missing = sorted(set(expected.table_counts) - set(actual.table_counts))
        extra = sorted(set(actual.table_counts) - set(expected.table_counts))
        count_mismatches = {
            name: (expected.table_counts[name], actual.table_counts.get(name))
            for name in expected.table_counts
            if expected.table_counts[name] != actual.table_counts.get(name)
        }
        raise RuntimeError(
            f"Restore verification failed: head={expected.migration_head}/{actual.migration_head}; "
            f"missing={missing}; extra={extra}; count_mismatches={count_mismatches}"
        )
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a restored database with its source")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--restored-url", required=True)
    args = parser.parse_args()
    result = verify_restore(create_engine(args.source_url), create_engine(args.restored_url))
    print(
        f"Restore verified at migration {result.migration_head}: "
        f"{len(result.table_counts)} tables, {sum(result.table_counts.values())} rows"
    )


if __name__ == "__main__":
    main()
