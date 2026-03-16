"""Baseline revision matching existing schema managed by setup_databases.py.

This migration is intentionally a no-op and serves as the Alembic baseline.
Future schema changes should be expressed as new Alembic revisions.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v1_0_0_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing schema (tables, indexes) is created by backend/setup_databases.py.
    # We treat that state as the Alembic baseline.
    pass


def downgrade() -> None:
    # Baseline is not reversible via Alembic; use future revisions for changes.
    pass

