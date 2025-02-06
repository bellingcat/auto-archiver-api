"""rename sheets last_archived col

Revision ID: 1636724ec4b1
Revises: a23aaf3ae930
Create Date: 2025-02-05 19:19:01.984396

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1636724ec4b1'
down_revision = 'a23aaf3ae930'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('sheets')]
    if 'last_archived_at' in columns:
        op.alter_column('sheets', 'last_archived_at', new_column_name='last_url_archived_at')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('sheets')]
    if 'last_url_archived_at' in columns:
        op.alter_column('sheets', 'last_url_archived_at', new_column_name='last_archived_at')
