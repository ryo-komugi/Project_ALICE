# Backward compatibility shim for core.session_manager -> gateway.session
from gateway.session import Session, SessionManager

__all__ = ["Session", "SessionManager"]
