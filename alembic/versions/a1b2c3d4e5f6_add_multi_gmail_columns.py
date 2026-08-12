"""add provider_account_id and is_active to oauth_tokens

Revision ID: a1b2c3d4e5f6
Revises: fc806ea58341
Create Date: 2026-08-06 11:25:00.000000

Adds two columns to oauth_tokens to support multi-account linking per provider:
  - provider_account_id: stable provider-side account ID (Google sub / GitHub user ID)
  - is_active: which account's token tools should use by default

Also updates the unique constraint from (user_id, provider) to
(user_id, provider, provider_account_id) so multiple accounts per provider are allowed.

The constraint rename preserves a no-op upgrade/downgrade path:
  upgrade:   drop old uq, add columns, add new uq
  downgrade: drop new uq, drop columns, restore old uq
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fc806ea58341'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the old unique constraint (user_id, provider)
    op.drop_constraint('uq_oauth_tokens_user_provider', 'oauth_tokens', type_='unique')

    # 2. Add provider_account_id column (nullable initially so existing rows don't break)
    op.add_column(
        'oauth_tokens',
        sa.Column('provider_account_id', sa.String(length=128), nullable=True),
    )

    # 3. Backfill existing rows: use provider_username as a fallback account ID
    #    so they don't violate the new unique constraint
    op.execute(
        """
        UPDATE oauth_tokens
        SET provider_account_id = COALESCE(provider_username, id::text)
        WHERE provider_account_id IS NULL
        """
    )

    # 4. Add is_active column (default True — all existing accounts are active)
    op.add_column(
        'oauth_tokens',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),
    )

    # 5. Create the new unique constraint (user_id, provider, provider_account_id)
    op.create_unique_constraint(
        'uq_oauth_tokens_user_provider_account',
        'oauth_tokens',
        ['user_id', 'provider', 'provider_account_id'],
    )


def downgrade() -> None:
    # 1. Drop the new constraint
    op.drop_constraint('uq_oauth_tokens_user_provider_account', 'oauth_tokens', type_='unique')

    # 2. Drop the new columns
    op.drop_column('oauth_tokens', 'is_active')
    op.drop_column('oauth_tokens', 'provider_account_id')

    # 3. Restore the original unique constraint
    op.create_unique_constraint(
        'uq_oauth_tokens_user_provider',
        'oauth_tokens',
        ['user_id', 'provider'],
    )
