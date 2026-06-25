"""eval data model

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25

Creates the four eval tables and the eval_run_status enum. The enum is created
and dropped explicitly (the same discipline as 0001's release_stage) so
`alembic downgrade base` leaves no orphaned type behind.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVAL_RUN_STATUS = postgresql.ENUM(
    "running",
    "succeeded",
    "failed",
    name="eval_run_status",
)


def upgrade() -> None:
    EVAL_RUN_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "eval_datasets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("generator_seed", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "eval_cases",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("input_path", sa.String(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("expected_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "input_path", name="uq_eval_cases_dataset_path"),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="eval_run_status", create_type=False),
            nullable=False,
        ),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"]),
        sa.ForeignKeyConstraint(["release_id"], ["releases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "eval_results",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("pass_fail", sa.Boolean(), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["eval_cases.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["eval_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("eval_cases")
    op.drop_table("eval_datasets")
    EVAL_RUN_STATUS.drop(op.get_bind(), checkfirst=True)
