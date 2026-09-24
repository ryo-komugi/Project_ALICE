# Backward compatibility shim
import sys
import gateway.profile as _target
from gateway.profile import Profile
sys.modules[__name__] = _target
