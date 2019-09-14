"""add submission_result

Revision ID: 64eb873263b6
Revises: 1550d60e9261
Create Date: 2019-09-14 15:45:52.593164

"""

# revision identifiers, used by Alembic.
revision = '64eb873263b6'
down_revision = '1550d60e9261'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('submission_result',
        sa.Column('submission_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('application_version', sa.String(), nullable=True),
        sa.Column('fingerprint_id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('meta_id', sa.Integer(), nullable=True),
        sa.Column('mbid', postgresql.UUID(), nullable=True),
        sa.Column('puid', postgresql.UUID(), nullable=True),
        sa.Column('foreignid', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('submission_id', name=op.f('submission_result_pkey'))
    )


def downgrade():
    op.drop_table('submission_result')
