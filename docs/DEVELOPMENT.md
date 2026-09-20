# Development

## Prerequisites

- Python 3.14.
- Docker CLI with a Docker-compatible engine for image builds and Kind image loading.
- Kind and kubectl for Kubernetes integration tests.

Docker Buildx is used by GitHub Actions for multi-architecture images but is not required for the local single-architecture integration test.

## Local checks

Create a virtual environment and install developer dependencies:

```bash
python3.14 -m venv .venv
. .venv/bin/activate
pip install --only-binary=:all: -e ".[dev]"
```

`uv.lock` records the complete, cross-platform dependency resolution used for supply-chain review. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the updated lockfile. CI installs only published wheels and rejects a dependency that is available only as a source distribution.

Run the same checks used by CI:

```bash
make format-check
make lint
make type-check
make test
```

The `tox` test command generates `coverage.xml`, `pytest-report.xml`, and `coverage_html/`. CI requires 100% statement and branch coverage for `app/`; coverage exclusions are not used to satisfy that gate.

The application applies a five-second client-side timeout to Kubernetes API calls. Set `KUBERNETES_REQUEST_TIMEOUT_SECONDS` to a positive number to exercise another value locally.

## Integration test

Build a local candidate image, then start a disposable Kind cluster and run the integration suite:

```bash
docker build -t kube-oidc-issuer-reflector:ci .
make test-integration
```

The test creates an API server with a deterministic issuer, deploys the local image, verifies effective service-account access, and compares reflected discovery and JWKS documents with the Kubernetes API server responses.

The script uses only the Docker CLI for container operations, runs the same rendered workload used by CI, and deletes the disposable cluster when it finishes. Set `IMAGE` or `CLUSTER_NAME` only when testing a differently tagged local image or avoiding a local Kind name collision.
