"""Compatibility import: authorization stays on the existing JWT session flow."""
from portal.auth import role_required

__all__ = ["role_required"]
