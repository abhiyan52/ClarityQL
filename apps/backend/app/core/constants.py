"""Application-wide constants."""

from uuid import UUID

# ──────────────────────────────────────────────────────────────────────
# Default Tenant
# ──────────────────────────────────────────────────────────────────────

# Default tenant ID for single-tenant usage
# All users will be assigned to this tenant by default
DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default Organization"
