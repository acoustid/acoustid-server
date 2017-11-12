"""Remove submission_id constraints

Revision ID: ae7e1e5763ef
Revises: d5c0520500a6
Create Date: 2017-11-12 13:18:02.175779

"""

# revision identifiers, used by Alembic.
revision = 'ae7e1e5763ef'
down_revision = 'd5c0520500a6'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.drop_constraint(u'fingerprint_source_fk_submission_id', 'fingerprint_source', type_='foreignkey')
    op.drop_constraint(u'track_foreignid_source_fk_submission_id', 'track_foreignid_source', type_='foreignkey')
    op.drop_constraint(u'track_mbid_source_fk_submission_id', 'track_mbid_source', type_='foreignkey')
    op.drop_constraint(u'track_meta_source_fk_submission_id', 'track_meta_source', type_='foreignkey')
    op.drop_constraint(u'track_puid_source_fk_submission_id', 'track_puid_source', type_='foreignkey')


def downgrade():
    op.create_foreign_key(u'track_puid_source_fk_submission_id', 'track_puid_source', 'submission', ['submission_id'], ['id'])
    op.create_foreign_key(u'track_meta_source_fk_submission_id', 'track_meta_source', 'submission', ['submission_id'], ['id'])
    op.create_foreign_key(u'track_mbid_source_fk_submission_id', 'track_mbid_source', 'submission', ['submission_id'], ['id'])
    op.create_foreign_key(u'track_foreignid_source_fk_submission_id', 'track_foreignid_source', 'submission', ['submission_id'], ['id'])
    op.create_foreign_key(u'fingerprint_source_fk_submission_id', 'fingerprint_source', 'submission', ['submission_id'], ['id'])
