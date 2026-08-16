"""drop retired favorites and emotion tables

Revision ID: 220bc65ffcdc
Revises: c32a99db4148
Create Date: 2026-08-16 00:00:00.000000

收藏夹、情绪画像、情绪记录功能已在 harness 瘦身中移除（参见 12a6cf8 / 2969ddb），
对应代码与 ORM 模型均已删除，这里补上 schema 层面的清理。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers used by Alembic.
revision: str = '220bc65ffcdc'
down_revision: Union[str, None] = 'c32a99db4148'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # favorites：功能已移除，drop 表 + 索引
    op.drop_index(op.f('ix_favorites_user_id'), table_name='favorites')
    op.drop_table('favorites')

    # emotion：emotion 子系统（profiles / records）已移除
    op.drop_index(op.f('ix_emotion_records_user_id'), table_name='emotion_records')
    op.drop_index(op.f('ix_emotion_records_emotion_type'), table_name='emotion_records')
    op.drop_index(op.f('ix_emotion_records_created_at'), table_name='emotion_records')
    op.drop_table('emotion_records')

    op.drop_index(op.f('ix_emotion_profiles_user_id'), table_name='emotion_profiles')
    op.drop_table('emotion_profiles')


def downgrade() -> None:
    from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint
    from sqlalchemy.dialects.postgresql import JSONB, UUID

    # 恢复 emotion 表
    op.create_table(
        'emotion_profiles',
        Column('id', UUID(), nullable=False),
        Column('user_id', UUID(), nullable=False),
        Column('dominant_emotion', String(length=32), nullable=False),
        Column('avg_valence', Float(), nullable=False),
        Column('avg_arousal', Float(), nullable=False),
        Column('sample_count', Integer(), nullable=False),
        Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        ForeignKey(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        UniqueConstraint('user_id', name='uq_emotion_profile_user'),
    )
    op.create_index(op.f('ix_emotion_profiles_user_id'), 'emotion_profiles', ['user_id'])

    op.create_table(
        'emotion_records',
        Column('id', UUID(), nullable=False),
        Column('user_id', UUID(), nullable=False),
        Column('conversation_id', UUID(), nullable=True),
        Column('message_id', UUID(), nullable=True),
        Column('emotion_type', String(length=32), nullable=False),
        Column('intensity', Float(), nullable=False),
        Column('valence', Float(), nullable=False),
        Column('arousal', Float(), nullable=False),
        Column('keywords', JSONB(astext_type=Text()), nullable=True),
        Column('trigger', String(length=255), nullable=True),
        Column('summary', Text(), nullable=True),
        Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        ForeignKey(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_emotion_records_created_at'), 'emotion_records', ['created_at'])
    op.create_index(op.f('ix_emotion_records_emotion_type'), 'emotion_records', ['emotion_type'])
    op.create_index(op.f('ix_emotion_records_user_id'), 'emotion_records', ['user_id'])

    # 恢复 favorites 表
    op.create_table(
        'favorites',
        Column('id', UUID(), nullable=False),
        Column('user_id', UUID(), nullable=False),
        Column('target_type', String(length=16), nullable=False),
        Column('target_id', String(length=64), nullable=False),
        Column('snapshot', JSONB(astext_type=Text()), nullable=True),
        Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        ForeignKey(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        UniqueConstraint('user_id', 'target_type', 'target_id', name='uq_favorite'),
    )
    op.create_index(op.f('ix_favorites_user_id'), 'favorites', ['user_id'])
