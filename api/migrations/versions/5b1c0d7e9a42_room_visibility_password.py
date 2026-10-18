"""room visibility and password

Revision ID: 5b1c0d7e9a42
Revises: 2822a2cbf379
Create Date: 2026-10-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b1c0d7e9a42'
down_revision: Union[str, Sequence[str], None] = '2822a2cbf379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Existing rooms stay public: the server default fills them in."""
    op.add_column('room', sa.Column('visibility', sa.String(length=8), server_default='public', nullable=False))
    op.add_column('room', sa.Column('password_hash', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('room', 'password_hash')
    op.drop_column('room', 'visibility')
