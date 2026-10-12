# Development

## Prerequisites

- Python 3.14.
- Docker CLI with a Docker-compatible engine for image builds and Kind image loading.
- Kind, kubectl, and Helm for Kubernetes integration tests. CI uses Helm 4.3.0.

Docker Buildx is used by GitHub Actions for multi-architecture images but is not required for the local single-architecture integration test.

## Local checks

Create a virtual environment and install developer dependencies:

```bash
python3.14 -m venv .venv
. .venv/bin/activate
pip install --only-binary=:all: '.[dev]'
```

`pyproject.toml` defines the application version and dependency constraints. The Docker build installs the runtime dependencies from the PEP 751 lock file `pylock.toml` with `--require-hashes`, so every wheel is verified against the lock during the build. The development tooling (pytest, ruff, mypy, tox, pip-audit, ...) lives in the `dev` extra and is never part of the lock or the image. Dependabot checks Python, Docker, and GitHub Actions dependencies weekly. Dependabot does not maintain `pylock.toml`, so regenerate it from `pyproject.toml` when runtime dependencies change; the daily security workflow audits the installed dependency set. For a release, update `project.version` in `pyproject.toml`, then run `python scripts/sync_release_version.py` to synchronize the pinned static deployment image.

## Dependency lock (`pylock.toml`)

`pylock.toml` is the single committed source of truth for the resolved runtime dependency tree: exact versions and a SHA-256 hash per wheel, per the [PEP 751 lock-file format](https://packaging.python.org/en/latest/specifications/pylock-toml/). It is generated from `pyproject.toml` and is the only lock file in the repository:

- The Docker build installs with `pip install --require-hashes -r pylock.toml`, so a tampered or mismatched runtime wheel fails the build.
- The `dependencies` security scan (pip-audit) installs the full `.[dev]` set from `pyproject.toml` (runtime + dev tooling) rather than the lock, because the lock is runtime-only and the audit must also cover the dev dependencies.
- The `lock-freshness` job in CI regenerates the lock and fails the build if `pylock.toml` does not match the manifest, so the lock can never silently drift from `pyproject.toml`.
- `uv.lock` is a transient intermediate of `uv export` and is intentionally **not** committed (see `.gitignore`); `pylock.toml` replaces it.

To update the lock (dependency upgrades, CVE fixes, new dependencies):

```bash
# 1. Change pyproject.toml (pin, bump, or add the dependency)

# 2. Regenerate the lock (requires the standalone uv binary on PATH;
#    the dev extra is an optional-dependency group, so uv export
#    excludes it from the runtime lock by default — no flag needed)
uv export --format pylock.toml --no-emit-project > pylock.toml

# 3. Sanity check: deterministic regeneration must reproduce the same file
uv export --format pylock.toml --no-emit-project | diff - pylock.toml

# 4. Run the checks (CI will verify the lock is in sync and install from it)
make all
```

Commit `pyproject.toml` and `pylock.toml` together in the same pull request; CI rejects any PR where the two are out of sync.

Docker and CI install only wheel distributions and reject a dependency that is available only as a source distribution.

Run the same checks used by CI:

```bash
make format-check
make lint
make type-check
make test
make test-helm
```

The `tox` test command generates `coverage.xml`, `pytest-report.xml`, and `coverage_html/`. CI requires 100% statement and branch coverage for `app/`; coverage exclusions are not used to satisfy that gate.

`make test-helm` packages the chart with the project version and checks application overrides, deployment settings, ServiceAccount/RBAC combinations, Ingress, Gateway API routes, and invalid configuration combinations. Use `HELM_BIN` to select a specific Helm binary.

`make test-integration` builds a temporary Kind cluster, deploys the local image using both static manifests and the packaged Helm chart, and checks OIDC endpoint reflection, authorization, and access-log handling of a normalized `X-Forwarded-For` header for each deployment. Its cache scenario removes the workload's discovery permissions after warming the cache and verifies that stale documents remain available during the resulting API errors. The suite does not deploy an external ingress or load balancer, so it cannot verify source-IP preservation before traffic reaches the application; validate that edge path in the target cluster. Every integration operation selects the designated Kind context explicitly, and the tests reject a context without the expected test issuer. It requires Docker or a Docker-compatible Podman socket.

The application applies a five-second client-side timeout to Kubernetes API calls. Set `KUBERNETES_REQUEST_TIMEOUT_SECONDS` to a positive number to exercise another value locally.

## Integration test

Build a local candidate image, then start a disposable Kind cluster and run the integration suite:

```bash
docker build -t kube-oidc-issuer-reflector:ci .
make test-integration
```

The test creates an API server with a deterministic issuer, deploys the local image, verifies effective service-account access, and compares reflected discovery and JWKS documents with the Kubernetes API server responses.

The script uses only the Docker CLI for container operations, runs the same rendered workload used by CI, and deletes the disposable cluster when it finishes. Set `IMAGE` or `CLUSTER_NAME` only when testing a differently tagged local image or avoiding a local Kind name collision. Custom test cluster names must start with `oidc-reflector-` to satisfy the integration guard.

When using Podman, connect the Docker CLI to its Docker-compatible socket and pass the image's full saved name. A Podman build tagged `kube-oidc-issuer-reflector:ci` is normally stored as `localhost/kube-oidc-issuer-reflector:ci`; run `IMAGE=localhost/kube-oidc-issuer-reflector:ci make test-integration` for that image. Set `KUBECONFIG` to a temporary file if you want to keep the test cluster out of your regular kubeconfig.
