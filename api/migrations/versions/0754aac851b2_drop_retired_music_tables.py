"""drop retired music tables

Revision ID: 0754aac851b2
Revises: 58b7b7115747

The music recommendation/player feature has been removed from the application.
This migration removes its remaining PostgreSQL tables while keeping the
historical migration chain intact.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0754aac851b2"
down_revision: Union[str, None] = "58b7b7115747"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("play_histories")
    op.drop_table("songs")


def downgrade() -> None:
    op.create_table(
        "songs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist", sa.String(length=255), nullable=False),
        sa.Column("album", sa.String(length=255), nullable=True),
        sa.Column("file_key", sa.String(length=512), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("lyric", sa.Text(), nullable=True),
        sa.Column("valence", sa.Float(), nullable=False),
        sa.Column("arousal", sa.Float(), nullable=False),
        sa.Column(
            "mood_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("tag_status", sa.String(length=16), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("playable", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_songs_created_at"), "songs", ["created_at"], unique=False)
    op.create_index(op.f("ix_songs_title"), "songs", ["title"], unique=False)
    op.create_index(op.f("ix_songs_user_id"), "songs", ["user_id"], unique=False)

    op.create_table(
        "play_histories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("song_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist", sa.String(length=255), nullable=False),
        sa.Column(
            "played_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_play_histories_played_at"),
        "play_histories",
        ["played_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_play_histories_user_id"),
        "play_histories",
        ["user_id"],
        unique=False,
    )
