"""remove recording_acoustid

Revision ID: 1550d60e9261
Revises: f99ba0e4ed97
Create Date: 2019-09-14 15:28:45.868715

"""

# revision identifiers, used by Alembic.
revision = '1550d60e9261'
down_revision = 'f99ba0e4ed97'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.drop_index('recording_acoustid_idx_acoustid', table_name='recording_acoustid')
    op.drop_index('recording_acoustid_idx_uniq', table_name='recording_acoustid')
    op.drop_table('recording_acoustid')


def downgrade():
    op.create_table('recording_acoustid',
        sa.Column('id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('acoustid', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('recording', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('disabled', sa.BOOLEAN(), server_default=sa.text(u'false'), autoincrement=False, nullable=False),
        sa.Column('created', postgresql.TIMESTAMP(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), autoincrement=False, nullable=False),
        sa.Column('updated', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=u'recording_acoustid_pkey')
    )
    op.create_index('recording_acoustid_idx_uniq', 'recording_acoustid', ['recording', 'acoustid'], unique=True)
    op.create_index('recording_acoustid_idx_acoustid', 'recording_acoustid', ['acoustid'], unique=False)
