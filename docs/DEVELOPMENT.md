# Development

## Prerequisites

- Python 3.14.
- Docker with Buildx for image builds.
- Kind and kubectl for Kubernetes integration tests.

## Local checks

Create a virtual environment and install developer dependencies:

```bash
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Run the same checks used by CI:

```bash
make format-check
make lint
make type-check
make test
```

The `tox -e py314` test command generates `coverage.xml`, `pytest-report.xml`, and `coverage_html/`. Unit tests require at least 95% branch coverage.

## Integration test

Build a local candidate image, then start a disposable Kind cluster and run the integration suite:

```bash
docker build -t kube-oidc-issuer-reflector:ci .
make test-integration
```

The test creates an API server with a deterministic issuer, deploys the local image, verifies effective service-account access, and compares reflected discovery and JWKS documents with the Kubernetes API server responses.
