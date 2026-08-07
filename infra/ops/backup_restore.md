# Backup and restore drill

This runbook is intentionally provider-neutral. The production operator must
configure managed PostgreSQL backups, point-in-time recovery, object lifecycle
policies, and alerting in the deployed cloud environment.

## PostgreSQL backup

```powershell
pg_dump --format=custom --no-owner --file=smriti-<timestamp>.dump $env:DATABASE_URL
```

Store the dump in a restricted, encrypted backup location. Never commit dumps
or upload them to an unapproved personal workstation.

## Restore drill

1. Provision an isolated PostgreSQL instance from the same major version.
2. Restore the dump into the isolated instance:

```powershell
pg_restore --clean --if-exists --no-owner --dbname=$env:RESTORE_DATABASE_URL smriti-<timestamp>.dump
```

3. Run `alembic current`, `alembic check`, and the read-only health/timeline smoke tests.
4. Verify patient counts, fact counts, contradiction counts, and representative encrypted-object references.
5. Record restore duration, data-loss window, and any manual steps.

## Object storage recovery

- Enable bucket versioning and customer-managed encryption where required.
- Configure lifecycle retention and deletion policies separately from application cleanup.
- Test restoring a representative report object into an isolated bucket.
- Verify application deletion removes both database references and stored objects.

## Release gate

Do not claim disaster-recovery readiness until a restore drill has succeeded,
been timed, and been reviewed by the service owner. Backups do not replace
patient-deletion procedures or incident-response obligations.
