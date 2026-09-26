# Development

## Prerequisites

- Python 3.14.
- `uv` for lockfile and release-version synchronization.
- Docker CLI with a Docker-compatible engine for image builds and Kind image loading.
- Kind, kubectl, and Helm for Kubernetes integration tests. CI uses Helm 3.22.0.

Docker Buildx is used by GitHub Actions for multi-architecture images but is not required for the local single-architecture integration test.

## Local checks

Create a virtual environment and install developer dependencies:

```bash
python3.14 -m venv .venv
. .venv/bin/activate
pip install --only-binary=:all: --require-hashes --requirement requirements-dev.lock
pip install --no-deps -e .
```

`uv.lock` records the complete, cross-platform dependency resolution used for supply-chain review. `requirements.lock` and `requirements-dev.lock` are hashed pip exports consumed by the image and CI. After changing dependencies in `pyproject.toml`, regenerate all three files:

```bash
uv lock
uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file requirements.lock
uv export --frozen --all-extras --no-emit-project --format requirements.txt --output-file requirements-dev.lock
```

For an application release, update `project.version` in `pyproject.toml`, then run `python scripts/sync_release_version.py` to regenerate `uv.lock` and synchronize the pinned static deployment image.

CI installs only these hashes from published wheels and rejects a dependency that is available only as a source distribution.

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

`make test-integration` builds a temporary Kind cluster, deploys the local image using both static manifests and the packaged Helm chart, and checks OIDC endpoint reflection and authorization for each deployment. Its cache scenario removes the workload's discovery permissions after warming the cache and verifies that stale documents remain available during the resulting API errors. Every integration operation selects the designated Kind context explicitly, and the tests reject a context without the expected test issuer. It requires Docker or a Docker-compatible Podman socket.

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
