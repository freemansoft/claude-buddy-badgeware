"""Shared by every test module: ROOT, the repository root, and sys.path
entries so the tests import the app's modules by bare name, as the badge
does, and the tools as the scripts in tools/ import each other.

`unittest discover -s tests` puts tests/ on sys.path, so `import support`
works from any folder under it."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _folder in (ROOT / "tools", ROOT / "apps" / "claude_buddy"):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))
