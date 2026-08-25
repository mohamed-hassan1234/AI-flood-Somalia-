# Backup and restore runbook

Production operators must use provider-managed encryption and retention policy.

1. Place the application in maintenance/read-only mode for a consistency test.
2. Create a MySQL logical backup using a least-privilege backup identity.
3. Record the schema migration head and object-storage version/checksum manifest.
4. Encrypt the backup and store it in an isolated retention-controlled bucket.
5. Restore into a newly provisioned non-production MySQL instance.
6. Run `alembic current`, integrity queries, and the critical workflow suite.
7. Compare row counts and sampled hashes; record operator, timing, and evidence.

A backup is not considered valid until a restore exercise succeeds. This document
does not claim that a production restore has occurred.

## Automated synthetic restore exercise

CI provisions MySQL 8.4, applies every migration, runs the explicitly synthetic development
seed, creates a `mysqldump --single-transaction` logical backup, restores it into a newly created
database, and runs:

```bash
python -m scripts.verify_restore --source-url "$SOURCE_DATABASE_URL" --restored-url "$RESTORED_DATABASE_URL"
```

The verifier requires identical Alembic heads, application-table sets, and row counts. It never
prints row contents or connection URLs. This catches incomplete dumps and wrong-schema restores,
but it is not evidence of provider encryption, object-storage recovery, production-scale timing,
or a witnessed production restore. Operators must still execute and record the seven-step exercise
above against an isolated environment using approved credentials and retention controls.
