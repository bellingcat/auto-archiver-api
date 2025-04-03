"""add new service_account_email column to groups table

Revision ID: 63ac79df4ad0
Revises: 02b2f6d17ed0
Create Date: 2025-02-11 21:53:23.293274

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "63ac79df4ad0"
down_revision = "02b2f6d17ed0"
branch_labels = None
depends_on = None

NEW_COL = "service_account_email"
TABLE = "groups"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(TABLE)]

    if NEW_COL not in columns:
        op.add_column(
            TABLE, sa.Column(NEW_COL, sa.String, nullable=True, default=None)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(TABLE)]
    if NEW_COL in columns:
        op.drop_column(TABLE, NEW_COL)
