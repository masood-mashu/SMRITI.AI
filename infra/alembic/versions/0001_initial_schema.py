"""Create the Smriti append-only health memory schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "patients",
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "reports",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.patient_id"), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("file_url", sa.Text()),
        sa.Column("raw_extraction", postgresql.JSONB()),
    )
    op.create_table(
        "health_facts",
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.patient_id"), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.report_id")),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("fact_key", sa.Text(), nullable=False),
        sa.Column("fact_value", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text()),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("is_emergency_relevant", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("health_facts.fact_id")),
        sa.Column("confidence", sa.REAL()),
    )
    op.create_index("idx_facts_current", "health_facts", ["patient_id", "fact_key"], unique=True, postgresql_where=sa.text("superseded_by IS NULL"))
    op.create_index("idx_facts_timeline", "health_facts", ["patient_id", "effective_date"])
    op.create_table(
        "contradictions",
        sa.Column("contradiction_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.patient_id"), nullable=False),
        sa.Column("fact_id_older", postgresql.UUID(as_uuid=True), sa.ForeignKey("health_facts.fact_id"), nullable=False),
        sa.Column("fact_id_newer", postgresql.UUID(as_uuid=True), sa.ForeignKey("health_facts.fact_id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contradictions")
    op.drop_index("idx_facts_timeline", table_name="health_facts")
    op.drop_index("idx_facts_current", table_name="health_facts")
    op.drop_table("health_facts")
    op.drop_table("reports")
    op.drop_table("patients")
