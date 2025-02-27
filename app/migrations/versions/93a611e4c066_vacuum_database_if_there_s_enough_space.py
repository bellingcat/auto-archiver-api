"""vacuum database (if there's enough space)

Revision ID: 93a611e4c066
Revises: 9369a264945b
Create Date: 2023-12-20 18:33:27.132566

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "93a611e4c066"
down_revision = "9369a264945b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        with op.get_context().autocommit_block():
            op.execute("VACUUM")
    except Exception as e:
        print(
            "Unable to run vacuum, maybe there's not enough disk space. it should be 2x the size of the database"
        )
        print(e)


def downgrade() -> None:
    pass
