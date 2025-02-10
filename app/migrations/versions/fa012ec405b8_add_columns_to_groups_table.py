"""add columns to groups table

Revision ID: fa012ec405b8
Revises: 93a611e4c066
Create Date: 2024-10-31 09:36:50.360710

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'fa012ec405b8'
down_revision = '93a611e4c066'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('groups')]

    if 'description' not in columns:
        op.add_column('groups', sa.Column('description', sa.String(), nullable=True))
    if 'orchestrator' not in columns:
        op.add_column('groups', sa.Column('orchestrator', sa.String(), nullable=True))
    if 'orchestrator_sheet' not in columns:
        op.add_column('groups', sa.Column('orchestrator_sheet', sa.String(), nullable=True))
    if 'permissions' not in columns:
        op.add_column('groups', sa.Column('permissions', sa.JSON(), nullable=True))
    if 'domains' not in columns:
        op.add_column('groups', sa.Column('domains', sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('groups')]

    column_names = ['description', 'orchestrator', 'orchestrator_sheet', 'permissions', 'domains']
    for column_name in column_names:
        if column_name in columns:
            op.drop_column('groups', column_name)
