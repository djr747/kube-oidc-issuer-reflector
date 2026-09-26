#!/usr/bin/env bash
set -euo pipefail

# Run only after the static-manifest suite in the same disposable Kind cluster.
INTEGRATION_CONTEXT="${INTEGRATION_CONTEXT:?Set the disposable Kind context}"
[[ "$INTEGRATION_CONTEXT" == kind-oidc-reflector-* ]]
MANIFEST="${MANIFEST:?Set the static integration manifest path}"
IMAGE="${IMAGE:?Set the loaded candidate image tag}"
PYTHON="${PYTHON:-python3}"
HELM_BIN="${HELM_BIN:-helm}"
CHART_ARCHIVE="${CHART_ARCHIVE:-}"

if [ -z "$CHART_ARCHIVE" ]; then
  VERSION="$("$PYTHON" -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")"
  CHART_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/oidc-reflector-chart.XXXXXX")"
  "$HELM_BIN" package charts/kube-oidc-issuer-reflector --version "$VERSION" --app-version "$VERSION" --destination "$CHART_DIR"
  CHART_ARCHIVE="$CHART_DIR/kube-oidc-issuer-reflector-$VERSION.tgz"
fi

kubectl --context "$INTEGRATION_CONTEXT" delete -f "$MANIFEST" --wait=true
"$HELM_BIN" upgrade --install kube-oidc-issuer-reflector "$CHART_ARCHIVE" \
  --kube-context "$INTEGRATION_CONTEXT" \
  --namespace kube-oidc-issuer-reflector --create-namespace \
  --set-string image.repository="${IMAGE%:*}" \
  --set-string image.tag="${IMAGE##*:}" \
  --set image.pullPolicy=Never \
  --set config.gunicornProcesses=1 \
  --set oidcDocumentCache.ttlSeconds=0 \
  --set oidcDocumentCache.staleIfErrorSeconds=300 \
  --set oidcDocumentCache.errorBackoffSeconds=30 \
  --wait --timeout 180s
"$PYTHON" -m pytest -m integration tests/integration/ -v
