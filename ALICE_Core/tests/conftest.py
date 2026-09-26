import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CORE_ROOT.parent

for p in [str(CORE_ROOT), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)
