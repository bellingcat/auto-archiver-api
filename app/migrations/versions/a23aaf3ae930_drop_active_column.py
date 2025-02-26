"""drop active column

Revision ID: a23aaf3ae930
Revises: 89121d2c96d8
Create Date: 2025-02-04 12:19:20.753570

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a23aaf3ae930'
down_revision = '89121d2c96d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]

    if 'is_active' in columns:
        op.drop_column('users', 'is_active')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]

    if 'is_active' not in columns:
        op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()))
