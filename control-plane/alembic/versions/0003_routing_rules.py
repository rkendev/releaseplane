"""routing rules

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-26

Creates the routing_rules table. The predicate is stored as JSONB (validated by
the RoutingRulePredicate schema on create), so no native enum is introduced and
the table is dropped cleanly on downgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routing_rules",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("use_case", sa.String(), nullable=False),
        sa.Column("predicate_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_model_config_id", sa.Uuid(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["target_model_config_id"], ["model_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("routing_rules")
