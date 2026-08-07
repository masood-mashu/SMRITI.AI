"""Add durable ingestion job status records."""

from alembic import op
import sqlalchemy as sa


revision = "0005_ingestion_jobs"
down_revision = "0004_patient_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"]),
        sa.ForeignKeyConstraint(["report_id"], ["reports.report_id"]),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "idx_ingestion_jobs_patient_status",
        "ingestion_jobs",
        ["patient_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ingestion_jobs_patient_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
