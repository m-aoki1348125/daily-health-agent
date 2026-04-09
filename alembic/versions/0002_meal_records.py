"""meal records and nutrition fields

Revision ID: 0002_meal_records
Revises: 0001_initial
Create Date: 2026-04-08 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_meal_records"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    daily_metric_columns = {
        column["name"] for column in inspector.get_columns("daily_metrics")
    }
    if "meal_calories" not in daily_metric_columns:
        op.add_column("daily_metrics", sa.Column("meal_calories", sa.Integer(), nullable=True))

    trend_feature_columns = {
        column["name"] for column in inspector.get_columns("trend_features")
    }
    if "meal_calories_vs_7d_avg" not in trend_feature_columns:
        op.add_column(
            "trend_features",
            sa.Column("meal_calories_vs_7d_avg", sa.Float(), nullable=True),
        )

    existing_tables = set(inspector.get_table_names())
    if "meal_records" not in existing_tables:
        op.create_table(
            "meal_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("source_message_id", sa.String(length=128), nullable=False),
            sa.Column("meal_date", sa.Date(), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("line_user_id", sa.String(length=128), nullable=False),
            sa.Column("image_mime_type", sa.String(length=64), nullable=False),
            sa.Column("estimated_calories", sa.Integer(), nullable=False),
            sa.Column("confidence", sa.String(length=32), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("meal_items_json", sa.JSON(), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("image_drive_file_id", sa.String(length=255), nullable=True),
            sa.Column("analysis_drive_file_id", sa.String(length=255), nullable=True),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("model_name", sa.String(length=128), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("meal_records")}
    if "ix_meal_records_source_message_id" not in existing_indexes:
        op.create_index(
            "ix_meal_records_source_message_id",
            "meal_records",
            ["source_message_id"],
            unique=True,
        )
    if "ix_meal_records_meal_date" not in existing_indexes:
        op.create_index("ix_meal_records_meal_date", "meal_records", ["meal_date"], unique=False)
    if "ix_meal_records_consumed_at" not in existing_indexes:
        op.create_index(
            "ix_meal_records_consumed_at",
            "meal_records",
            ["consumed_at"],
            unique=False,
        )
    if "ix_meal_records_line_user_id" not in existing_indexes:
        op.create_index(
            "ix_meal_records_line_user_id",
            "meal_records",
            ["line_user_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_meal_records_line_user_id", table_name="meal_records")
    op.drop_index("ix_meal_records_consumed_at", table_name="meal_records")
    op.drop_index("ix_meal_records_meal_date", table_name="meal_records")
    op.drop_index("ix_meal_records_source_message_id", table_name="meal_records")
    op.drop_table("meal_records")
    op.drop_column("trend_features", "meal_calories_vs_7d_avg")
    op.drop_column("daily_metrics", "meal_calories")
