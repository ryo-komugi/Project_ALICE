# Backward compatibility shim
import sys
import gateway.downloader as _target
from gateway.downloader import ContentDownloader
sys.modules[__name__] = _target
