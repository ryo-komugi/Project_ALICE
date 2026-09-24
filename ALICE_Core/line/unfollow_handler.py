# Backward compatibility shim
import sys
import gateway.handlers.unfollow as _target
from gateway.handlers.unfollow import UnfollowHandler
sys.modules[__name__] = _target
