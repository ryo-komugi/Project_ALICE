# Backward compatibility shim
import sys
import gateway.sender as _target
from gateway.sender import MessageSender
sys.modules[__name__] = _target
