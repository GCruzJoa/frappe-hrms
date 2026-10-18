"""Record exact application revisions without exporting credentials."""
import json
from pathlib import Path
import platform
import subprocess
import sys

root = Path("/home/frappe/frappe-bench")
apps = {}
for name in ("frappe", "erpnext", "hrms"):
    source = root / "apps" / name
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    apps[name] = {"commit": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "dirty_files": git("status", "--porcelain").splitlines()}
Path(sys.argv[1]).write_text(json.dumps({"apps": apps, "python": platform.python_version()}, indent=2) + "\n")
