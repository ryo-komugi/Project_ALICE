# Backward compatibility shim for core.viewer -> portal.viewer
import sys
import portal.viewer as _target
from portal.viewer import *
sys.modules[__name__] = _target
