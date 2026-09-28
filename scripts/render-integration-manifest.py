#!/usr/bin/env python3
"""Render an integration deployment manifest from the core production manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_MANIFEST = Path("deploy/deploy.yaml")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    with _MANIFEST.open() as stream:
        documents = list(yaml.safe_load_all(stream))

    rendered = []
    for document in documents:
        if not document:
            continue
        if document.get("kind") == "Deployment":
            container = document["spec"]["template"]["spec"]["containers"][0]
            container["image"] = args.image
            container["imagePullPolicy"] = "Never"
            container["env"] = [
                {"name": "GUNICORN_PROCESSES", "value": "1"},
                {"name": "OIDC_DOCUMENT_CACHE_TTL_SECONDS", "value": "0"},
                {"name": "OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS", "value": "300"},
                {"name": "OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS", "value": "30"},
            ]
        rendered.append(document)

    yaml.safe_dump_all(rendered, sys.stdout, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
