#!/usr/bin/env python3
"""Render a Kind-safe deployment manifest from the production manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--manifest", default="deploy/deploy.yaml")
    args = parser.parse_args()

    with Path(args.manifest).open() as stream:
        documents = list(yaml.safe_load_all(stream))

    rendered = []
    for document in documents:
        if not document or document.get("kind") == "Ingress":
            continue
        if document.get("kind") == "Deployment":
            container = document["spec"]["template"]["spec"]["containers"][0]
            container["image"] = args.image
            container["imagePullPolicy"] = "Never"
        rendered.append(document)

    yaml.safe_dump_all(rendered, sys.stdout, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
