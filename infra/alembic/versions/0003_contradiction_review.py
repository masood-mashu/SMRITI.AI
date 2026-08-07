"""Add human review metadata for contradictions."""

from alembic import op
import sqlalchemy as sa


revision = "0003_contradiction_review"
down_revision = "0002_unique_current_fact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contradictions", sa.Column("review_decision", sa.Text(), nullable=True))
    op.add_column("contradictions", sa.Column("reviewer_note", sa.Text(), nullable=True))
    op.add_column("contradictions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contradictions", sa.Column("reviewed_by", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contradictions", "reviewed_by")
    op.drop_column("contradictions", "reviewed_at")
    op.drop_column("contradictions", "reviewer_note")
    op.drop_column("contradictions", "review_decision")
