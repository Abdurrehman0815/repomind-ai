"""add repository_commit column to projects table

Revision ID: 002_add_repo_commit
Revises: 001_initial_schema
Create Date: 2026-10-14 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_repo_commit'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add repository_commit column to projects table
    op.add_column('projects', sa.Column('repository_commit', sa.String(length=64), nullable=True, index=True))


def downgrade() -> None:
    # Remove repository_commit column from projects table
    op.drop_column('projects', 'repository_commit')