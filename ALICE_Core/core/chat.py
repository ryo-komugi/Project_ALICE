# Backward compatibility shim for core.chat -> portal.chat_proxy
import sys
import portal.chat_proxy as _target
from portal.chat_proxy import *
sys.modules[__name__] = _target
