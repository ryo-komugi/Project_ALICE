# Backward compatibility shim for core.admin_auth -> portal.auth
import sys
import portal.auth as _target
from portal.auth import *
sys.modules[__name__] = _target
