#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-oidc-reflector-integration}"
IMAGE="${IMAGE:-kube-oidc-issuer-reflector:ci}"
MANIFEST="${RUNNER_TEMP:-/tmp}/oidc-reflector-manifest.yaml"
PYTHON="${PYTHON:-python3}"

cleanup() {
  kind export logs "${RUNNER_TEMP:-/tmp}/kind-logs" --name "$CLUSTER_NAME" || true
  kind delete cluster --name "$CLUSTER_NAME" || true
}
trap cleanup EXIT

kind create cluster --name "$CLUSTER_NAME" --config tests/integration/kind-config.yaml --wait 120s
kind load docker-image "$IMAGE" --name "$CLUSTER_NAME"
"$PYTHON" scripts/render-integration-manifest.py --image "$IMAGE" > "$MANIFEST"
kubectl apply -f "$MANIFEST"
kubectl -n kube-oidc-issuer-reflector rollout status deployment/kube-oidc-issuer-reflector --timeout=180s
"$PYTHON" -m pytest -m integration tests/integration/ -v
