# Backward compatibility shim
import sys
import gateway.handlers.follow as _target
from gateway.handlers.follow import FollowHandler
sys.modules[__name__] = _target
