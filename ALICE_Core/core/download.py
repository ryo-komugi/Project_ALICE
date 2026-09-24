# Backward compatibility shim for core.download -> portal.download
import sys
import portal.download as _target
from portal.download import *
sys.modules[__name__] = _target
