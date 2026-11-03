"""Add weekly meal plan reminder email preference

Revision ID: c3f8d5a1e2b4
Revises: b7e4a2d1c9f0
Create Date: 2026-11-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3f8d5a1e2b4'
down_revision = 'b7e4a2d1c9f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'household_members',
        sa.Column(
            'receive_weekly_reminder_emails',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column('household_members', 'receive_weekly_reminder_emails')
