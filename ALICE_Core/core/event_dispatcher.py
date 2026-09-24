# Backward compatibility shim for core.event_dispatcher -> gateway.dispatcher
from gateway.dispatcher import EventDispatcher

__all__ = ["EventDispatcher"]
