
"""Add line_number to dependencies.

Revision ID: 003_dep_line_number
Revises: 002_add_repo_commit
"""

from alembic import op
import sqlalchemy as sa


revision = "003_dep_line_number"
down_revision = "002_add_repo_commit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dependencies",
        sa.Column(
            "line_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # Existing rows receive 0; new inserts must supply
    # the appropriate source line number.
    op.alter_column(
        "dependencies",
        "line_number",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("dependencies", "line_number")
