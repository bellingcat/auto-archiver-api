"""created tasks.deleted column

Revision ID: ae468b023078
Revises: 
Create Date: 2023-02-27 12:40:24.146786

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ae468b023078'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tasks',
        sa.Column('deleted', sa.Boolean, default=False, nullable=False, server_default=sa.sql.expression.false()),
    )


def downgrade() -> None:
    op.drop_column('tasks', 'deleted')
