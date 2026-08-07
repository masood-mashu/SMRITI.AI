"""Store the metadata needed by asynchronous ingestion workers."""

from alembic import op
import sqlalchemy as sa


revision = "0006_ingestion_job_payload"
down_revision = "0005_ingestion_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("filename", sa.Text(), nullable=False, server_default="report"))
    op.add_column(
        "ingestion_jobs",
        sa.Column("content_type", sa.Text(), nullable=False, server_default="application/octet-stream"),
    )
    op.add_column("ingestion_jobs", sa.Column("use_fixture", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("ingestion_jobs", sa.Column("pii_redactions", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ingestion_jobs", sa.Column("pii_provider", sa.Text(), nullable=False, server_default="unknown"))


def downgrade() -> None:
    for name in ("pii_provider", "pii_redactions", "use_fixture", "content_type", "filename"):
        op.drop_column("ingestion_jobs", name)
