# Database migrations

Production uses Alembic. Apply the PostgreSQL migration chain with:

```bash
alembic upgrade head
```

The migration creates the append-only schema from `infra/schema.sql`, including
the `superseded_by` self-reference and partial current-facts index. Set
`DB_AUTO_CREATE=false` for deployed environments.

SQLite remains available for local development with automatic table creation;
it is not a production database target and should not be used with Alembic.
