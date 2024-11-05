"""add sheet_id to archive table

Revision ID: 89121d2c96d8
Revises: fa012ec405b8
Create Date: 2024-11-04 11:12:30.237299

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '89121d2c96d8'
down_revision = 'fa012ec405b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('archives')]

    if 'sheet_id' not in columns:
        with op.batch_alter_table('archives') as batch_op:
            batch_op.add_column(sa.Column('sheet_id', sa.String(), nullable=True, default=None))
            batch_op.create_foreign_key('fk_sheet_id', 'sheets', ['sheet_id'], ['id'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    foreign_keys = [fk['name'] for fk in inspector.get_foreign_keys('archives')]
    columns = [col['name'] for col in inspector.get_columns('archives')]

    with op.batch_alter_table('archives') as batch_op:
        if 'fk_sheet_id' in foreign_keys:
            batch_op.drop_constraint('fk_sheet_id', type_='foreignkey')

        if 'sheet_id' in columns:
            batch_op.drop_column('sheet_id')
