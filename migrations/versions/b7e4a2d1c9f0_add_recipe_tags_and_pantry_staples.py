"""Add recipe tags and pantry staples

Revision ID: b7e4a2d1c9f0
Revises: 00b31406199b
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7e4a2d1c9f0'
down_revision = '00b31406199b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'recipe_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('household_id', 'name', name='unique_household_tag'),
    )
    op.create_table(
        'recipe_tags_assoc',
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['recipe_tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('recipe_id', 'tag_id'),
    )
    op.create_table(
        'pantry_staples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('ingredient_name', sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('household_id', 'ingredient_name', name='unique_household_staple'),
    )


def downgrade():
    op.drop_table('pantry_staples')
    op.drop_table('recipe_tags_assoc')
    op.drop_table('recipe_tags')
