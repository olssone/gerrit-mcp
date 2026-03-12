import sys
from pathlib import Path

# Add src/gerrit_review_mcp/ to sys.path so tests can import server and config
# directly by module name (e.g. `from config import ...`, `from server import ...`)
_pkg = str(Path(__file__).parent.parent / "src" / "gerrit_review_mcp")
if _pkg not in sys.path:
  sys.path.insert(0, _pkg)
