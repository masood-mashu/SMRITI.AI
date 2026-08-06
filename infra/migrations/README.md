# Database migrations

`001_initial_schema.sql` is the baseline migration for a new Postgres database.
Apply it with `psql` or your Cloud SQL migration runner. Set `DB_AUTO_CREATE=false`
for deployed environments so application startup does not create tables implicitly.

