# Backward compatibility shim
import sys
import gateway.profile as _target
from gateway.profile import ProfileManager
sys.modules[__name__] = _target
