import sys
from pathlib import Path

# Add src/ to sys.path so tests can import server and config directly
# by module name (e.g. `from config import ...`, `from server import ...`)
_src = str(Path(__file__).parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
