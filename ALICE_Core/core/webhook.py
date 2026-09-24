# Backward compatibility shim for core.webhook -> gateway.webhook
from gateway.webhook import router

__all__ = ["router"]
