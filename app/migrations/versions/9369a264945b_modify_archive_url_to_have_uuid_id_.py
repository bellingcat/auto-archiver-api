"""modify archive url to have uuid id instead of url unique constraint

Revision ID: 9369a264945b
Revises:
Create Date: 2023-12-20 17:24:59.320691

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '9369a264945b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # since the primary key constraint is not named, we have to recreate it first
    with op.batch_alter_table("archive_urls") as batch_op:
        batch_op.create_primary_key("pk_url", ["url"])
        batch_op.drop_constraint("pk_url", type_='primary')
        batch_op.create_primary_key("pk_url_archive_id", ["url", "archive_id"])

def downgrade() -> None:
    with op.batch_alter_table("archive_urls") as batch_op:
        batch_op.drop_constraint("pk_url_archive_id", type_='primary')
        batch_op.create_primary_key("url", ["url"])
