_BINDINGS_IMPORT_ERROR = None

try:
    from .bindings import *  # noqa: F401,F403
    IS_AVAILABLE = True
except Exception as exc:
    IS_AVAILABLE = False
    _BINDINGS_IMPORT_ERROR = str(exc)
