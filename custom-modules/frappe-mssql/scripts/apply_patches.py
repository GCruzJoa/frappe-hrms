"""Apply an integration patch only to its recorded upstream preimage."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def apply(root, patch_dir, app="frappe"):
    root, patch_dir = Path(root), Path(patch_dir)
    manifest = json.loads((patch_dir / f"{app}-preimages.json").read_text())
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != manifest["commit"]:
        raise RuntimeError("Frappe commit differs from the reviewed patch baseline")
    for name, expected in manifest["files"].items():
        actual_hash = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual_hash != expected:
            raise RuntimeError(f"Upstream file differs from reviewed patch preimage: {name}")
    patch = str((patch_dir / f"{app}.patch").resolve())
    if not (patch_dir / f"{app}.patch").stat().st_size:
        return
    subprocess.run(["git", "-C", str(root), "apply", "--check", patch], check=True)
    subprocess.run(["git", "-C", str(root), "apply", patch], check=True)


if __name__ == "__main__":
    apply(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "frappe")
