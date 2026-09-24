# Backward compatibility shim with transparent mock support
import sys
import gateway.handlers.message as _target
from gateway.handlers.message import MessageHandler, WORKFLOW_MAP
sys.modules[__name__] = _target
