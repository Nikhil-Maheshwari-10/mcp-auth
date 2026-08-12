"""workspace_architecture — add workspaces, workspace_users; add active_workspace_id to sessions; add nullable workspace_id to oauth_tokens and audit_logs

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-07 10:00:00.000000

Workspaces are completely optional. Users log in directly without a forced workspace.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create workspaces table
    op.create_table(
        'workspaces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )

    # 2. Create workspace_users table
    op.create_table(
        'workspace_users',
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(32), nullable=False, server_default='owner'),
        sa.Column('joined_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('workspace_id', 'user_id'),
    )
    op.create_index('ix_workspace_users_user_id', 'workspace_users', ['user_id'])

    # 3. Add google_sub to users (if not exists)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='users' AND column_name='google_sub'
            ) THEN
                ALTER TABLE users ADD COLUMN google_sub VARCHAR(128) UNIQUE;
            END IF;
        END $$;
    """)

    # 4. Add nullable workspace_id to oauth_tokens (user_id remains primary owner)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='oauth_tokens' AND column_name='workspace_id'
            ) THEN
                ALTER TABLE oauth_tokens ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)

    # Ensure user_id column is present and nullable=False on oauth_tokens
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='oauth_tokens' AND column_name='user_id'
            ) THEN
                ALTER TABLE oauth_tokens ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)

    # 5. Add active_workspace_id to auth_sessions
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='auth_sessions' AND column_name='active_workspace_id'
            ) THEN
                ALTER TABLE auth_sessions ADD COLUMN active_workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)

    # 6. Add nullable workspace_id to audit_logs (user_id remains)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='audit_logs' AND column_name='workspace_id'
            ) THEN
                ALTER TABLE audit_logs ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='audit_logs' AND column_name='user_id'
            ) THEN
                ALTER TABLE audit_logs ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column('audit_logs', 'workspace_id')
    op.drop_column('auth_sessions', 'active_workspace_id')
    op.drop_column('oauth_tokens', 'workspace_id')
    op.drop_column('users', 'google_sub')
    op.drop_index('ix_workspace_users_user_id', 'workspace_users')
    op.drop_table('workspace_users')
    op.drop_table('workspaces')
