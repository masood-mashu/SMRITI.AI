"""Add patient timeline indexes for reports and contradictions."""

from alembic import op


revision = "0004_patient_query_indexes"
down_revision = "0003_contradiction_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_reports_patient", "reports", ["patient_id", "uploaded_at"])
    op.create_index("idx_contradictions_patient", "contradictions", ["patient_id", "detected_at"])


def downgrade() -> None:
    op.drop_index("idx_contradictions_patient", table_name="contradictions")
    op.drop_index("idx_reports_patient", table_name="reports")
