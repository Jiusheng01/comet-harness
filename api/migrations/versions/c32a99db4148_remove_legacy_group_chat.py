"""remove legacy group chat

Revision ID: c32a99db4148
Revises: 0754aac851b2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c32a99db4148"
down_revision: Union[str, None] = "0754aac851b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""DELETE FROM favorites f WHERE f.target_type='message' AND EXISTS (
        SELECT 1 FROM messages m JOIN conversations c ON c.id=m.conversation_id
        WHERE c.is_group IS TRUE AND f.target_id=m.id::text)""")
    op.execute("""DELETE FROM conversation_shares cs WHERE EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id=cs.conversation_id AND c.is_group IS TRUE)""")
    op.execute("""DELETE FROM emotion_records er WHERE EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id=er.conversation_id AND c.is_group IS TRUE)
        OR EXISTS (
        SELECT 1 FROM messages m JOIN conversations c ON c.id=m.conversation_id
        WHERE m.id=er.message_id AND c.is_group IS TRUE)""")
    op.execute("DELETE FROM conversations WHERE is_group IS TRUE")
    op.execute("DELETE FROM agent_personas WHERE in_group_only IS TRUE")

    op.drop_table("group_members")
    op.drop_table("persona_groups")
    op.drop_index(op.f("ix_conversations_join_code"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_is_group"), table_name="conversations")
    op.drop_column("messages", "sender_user_id")
    op.drop_column("messages", "sender_persona_id")
    op.drop_column("conversations", "join_code")
    op.drop_column("conversations", "enable_tools")
    op.drop_column("conversations", "member_persona_ids")
    op.drop_column("conversations", "is_group")
    op.drop_column("agent_personas", "in_group_only")


def downgrade() -> None:
    # Schema-only rollback; deleted legacy group-chat data is not restored.
    op.add_column("agent_personas", sa.Column(
        "in_group_only", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("agent_personas", "in_group_only", server_default=None)

    op.add_column("conversations", sa.Column(
        "is_group", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("conversations", "is_group", server_default=None)
    op.add_column("conversations", sa.Column(
        "member_persona_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("conversations", sa.Column(
        "enable_tools", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("conversations", "enable_tools", server_default=None)
    op.add_column("conversations", sa.Column(
        "join_code", sa.String(length=16), nullable=True))
    op.create_index(op.f("ix_conversations_is_group"), "conversations", ["is_group"])
    op.create_index(op.f("ix_conversations_join_code"), "conversations", ["join_code"])
    op.add_column("messages", sa.Column("sender_persona_id", sa.UUID(), nullable=True))
    op.add_column("messages", sa.Column("sender_user_id", sa.UUID(), nullable=True))

    op.create_table(
        "persona_groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False),
        sa.Column("member_persona_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enable_tools", sa.Boolean(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_persona_groups_user_id"), "persona_groups", ["user_id"])

    op.create_table(
        "group_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("nickname", sa.String(length=64), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_group_member"),
    )
    op.create_index(op.f("ix_group_members_conversation_id"), "group_members", ["conversation_id"])
    op.create_index(op.f("ix_group_members_user_id"), "group_members", ["user_id"])
