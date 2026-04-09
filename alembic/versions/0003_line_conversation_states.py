"""line conversation state table

Revision ID: 0003_line_conversation_states
Revises: 0002_meal_records
Create Date: 2026-04-09 10:40:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_line_conversation_states"
down_revision = "0002_meal_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "line_conversation_states" not in set(inspector.get_table_names()):
        op.create_table(
            "line_conversation_states",
            sa.Column("line_user_id", sa.String(length=128), primary_key=True, nullable=False),
            sa.Column("intent", sa.String(length=64), nullable=False),
            sa.Column("state_json", sa.JSON(), nullable=False),
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
    op.drop_table("line_conversation_states")
