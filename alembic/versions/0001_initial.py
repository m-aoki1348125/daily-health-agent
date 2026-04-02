"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-02 02:15:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("sleep_minutes", sa.Integer(), nullable=True),
        sa.Column("sleep_efficiency", sa.Float(), nullable=True),
        sa.Column("deep_sleep_minutes", sa.Integer(), nullable=True),
        sa.Column("rem_sleep_minutes", sa.Integer(), nullable=True),
        sa.Column("awakenings", sa.Integer(), nullable=True),
        sa.Column("resting_hr", sa.Integer(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("raw_drive_file_id", sa.String(length=255), nullable=True),
        sa.Column("bedtime_start", sa.String(length=32), nullable=True),
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
    op.create_table(
        "trend_features",
        sa.Column("date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("sleep_vs_14d_avg", sa.Float(), nullable=True),
        sa.Column("resting_hr_vs_30d_avg", sa.Float(), nullable=True),
        sa.Column("sleep_debt_streak_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bedtime_drift_minutes", sa.Float(), nullable=True),
        sa.Column("recovery_score", sa.Integer(), nullable=False, server_default="50"),
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
    op.create_table(
        "advice_history",
        sa.Column("date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_findings_json", sa.JSON(), nullable=False),
        sa.Column("today_actions_json", sa.JSON(), nullable=False),
        sa.Column("exercise_advice", sa.Text(), nullable=False),
        sa.Column("sleep_advice", sa.Text(), nullable=False),
        sa.Column("caffeine_advice", sa.Text(), nullable=False),
        sa.Column("medical_note", sa.Text(), nullable=False),
        sa.Column("long_term_comment", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("daily_report_drive_file_id", sa.String(length=255), nullable=True),
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
    op.create_table(
        "drive_index",
        sa.Column("date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("raw_file_id", sa.String(length=255), nullable=True),
        sa.Column("daily_json_file_id", sa.String(length=255), nullable=True),
        sa.Column("daily_md_file_id", sa.String(length=255), nullable=True),
        sa.Column("weekly_file_id", sa.String(length=255), nullable=True),
        sa.Column("monthly_file_id", sa.String(length=255), nullable=True),
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


def downgrade() -> None:
    op.drop_table("drive_index")
    op.drop_table("advice_history")
    op.drop_table("trend_features")
    op.drop_table("daily_metrics")
