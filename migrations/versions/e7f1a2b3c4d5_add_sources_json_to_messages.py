"""add_sources_json_to_messages

Revision ID: e7f1a2b3c4d5
Revises: 83e9daa3c009
Create Date: 2026-10-12 02:15:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "83e9daa3c009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("sources_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("sources_json")
