"""Make current facts unique per patient and fact key."""

from alembic import op
import sqlalchemy as sa


revision = "0002_unique_current_fact"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_facts_current", table_name="health_facts")
    op.create_index(
        "idx_facts_current",
        "health_facts",
        ["patient_id", "fact_key"],
        unique=True,
        postgresql_where=sa.text("superseded_by IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_facts_current", table_name="health_facts")
    op.create_index(
        "idx_facts_current",
        "health_facts",
        ["patient_id", "fact_key"],
        unique=True,
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
