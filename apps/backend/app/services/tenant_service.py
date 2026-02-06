"""Tenant utility functions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DEFAULT_TENANT_ID,
    DEFAULT_TENANT_NAME,
    DEFAULT_TENANT_SLUG,
)
from app.models.tenant import Tenant


async def get_or_create_default_tenant(session: AsyncSession) -> Tenant:
    """
    Get or create the default tenant.

    This ensures the default tenant exists, which is useful for:
    - Single-tenant deployments
    - Development/testing environments
    - Graceful handling of missing tenant data

    Returns:
        The default Tenant object
    """
    from sqlalchemy.exc import IntegrityError

    # Try to fetch existing default tenant
    result = await session.execute(
        select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        # Create default tenant if it doesn't exist
        tenant = Tenant(
            id=DEFAULT_TENANT_ID,
            name=DEFAULT_TENANT_NAME,
            slug=DEFAULT_TENANT_SLUG,
            is_active=True,
        )
        session.add(tenant)
        
        try:
            await session.flush()
        except IntegrityError:
            # Another concurrent request created the tenant first
            # Remove the failed tenant object from session without rolling back
            # This keeps the current transaction open for the caller
            session.expunge(tenant)
            result = await session.execute(
                select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID)
            )
            tenant = result.scalar_one()

    return tenant


async def get_default_tenant_id(session: AsyncSession) -> UUID:
    """
    Get the default tenant ID, creating the tenant if needed.

    Returns:
        UUID of the default tenant
    """
    tenant = await get_or_create_default_tenant(session)
    return tenant.id
