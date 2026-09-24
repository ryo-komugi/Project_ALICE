# Backward compatibility shim for core.session -> gateway.session
from gateway.session import Session

__all__ = ["Session"]
