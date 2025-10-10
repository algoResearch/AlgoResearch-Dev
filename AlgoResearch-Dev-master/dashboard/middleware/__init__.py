from .middleware import *  # re-export for backward-compat

try:
    from .role_redirect_middleware import RoleRedirectMiddleware
except Exception:
    pass
