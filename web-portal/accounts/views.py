"""Legacy account URLs reuse the Identity Service login/logout implementation."""
from portal.views import login_view, logout_view

__all__ = ["login_view", "logout_view"]
