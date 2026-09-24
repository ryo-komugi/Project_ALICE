import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SEARCH_DIR = TESTS_DIR.parent
PROJECT_DIR = SEARCH_DIR.parent
CORE_DIR = PROJECT_DIR / "ALICE_Core"

for p in [str(CORE_DIR), str(PROJECT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)
