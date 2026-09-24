# Backward compatibility shim for core.admin -> portal.admin
import sys
import portal.admin as _target
from portal.admin import *
sys.modules[__name__] = _target
