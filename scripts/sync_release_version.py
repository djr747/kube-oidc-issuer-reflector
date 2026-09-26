"""Regenerate release-version metadata from pyproject.toml."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_FILE = ROOT / "pyproject.toml"
DEPLOY_FILE = ROOT / "deploy" / "deploy.yaml"
IMAGE = "ghcr.io/djr747/kube-oidc-issuer-reflector"


def main() -> None:
    """Regenerate uv.lock and synchronize the pinned static deployment image."""
    project = tomllib.loads(PROJECT_FILE.read_text())
    version = project["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?", version):
        raise SystemExit(f"Unsupported release version: {version}")

    deployment = DEPLOY_FILE.read_text()
    pattern = re.compile(rf"(?m)^(\s*image:\s*{re.escape(IMAGE)}:)[^\s#]+")
    synchronized, count = pattern.subn(rf"\g<1>{version}", deployment)
    if count != 1:
        raise SystemExit(f"Expected one pinned {IMAGE} image in {DEPLOY_FILE}")

    subprocess.run(["uv", "lock"], cwd=ROOT, check=True)
    DEPLOY_FILE.write_text(synchronized)
    print(f"Synchronized uv.lock and deploy/deploy.yaml to application version {version}.")


if __name__ == "__main__":
    main()
