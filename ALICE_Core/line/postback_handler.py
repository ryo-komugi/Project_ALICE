# Backward compatibility shim
import sys
import gateway.handlers.postback as _target
from gateway.handlers.postback import PostbackHandler
sys.modules[__name__] = _target
