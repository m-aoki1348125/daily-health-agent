"""add body metrics

Revision ID: 0004_body_metrics
Revises: 0003_line_conversation_states
Create Date: 2026-05-02 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_body_metrics"
down_revision = "0003_line_conversation_states"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in existing_columns:
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing("daily_metrics", sa.Column("weight_kg", sa.Float(), nullable=True))
    _add_column_if_missing("daily_metrics", sa.Column("bmi", sa.Float(), nullable=True))
    _add_column_if_missing(
        "daily_metrics", sa.Column("body_fat_percent", sa.Float(), nullable=True)
    )
    _add_column_if_missing(
        "daily_metrics", sa.Column("body_logged_at", sa.String(length=32), nullable=True)
    )
    _add_column_if_missing(
        "trend_features", sa.Column("weight_kg_vs_30d_avg", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("trend_features", "weight_kg_vs_30d_avg")
    op.drop_column("daily_metrics", "body_logged_at")
    op.drop_column("daily_metrics", "body_fat_percent")
    op.drop_column("daily_metrics", "bmi")
    op.drop_column("daily_metrics", "weight_kg")
