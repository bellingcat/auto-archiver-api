"""create archives.store_until column

Revision ID: 02b2f6d17ed0
Revises: 1636724ec4b1
Create Date: 2025-02-08 15:22:20.392522

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '02b2f6d17ed0'
down_revision = '1636724ec4b1'
branch_labels = None
depends_on = None
STORE_UNTIL_COL = "store_until"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('archives')]

    if STORE_UNTIL_COL not in columns:
        op.add_column('archives', sa.Column(STORE_UNTIL_COL, sa.DateTime(), nullable=True, default=None))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('archives')]
    if STORE_UNTIL_COL in columns:
        op.drop_column('archives', STORE_UNTIL_COL)
