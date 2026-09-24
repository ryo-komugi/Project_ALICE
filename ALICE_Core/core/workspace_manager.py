# Backward compatibility shim for core.workspace_manager -> hub.workspace
from hub.workspace import WorkspaceManager

__all__ = ["WorkspaceManager"]
