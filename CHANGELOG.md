# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-07-30

### Added

- Full CI/CD pipeline with linting, type checking, branch-coverage reporting, and SonarCloud analysis.
- Unit test suite covering all application endpoints, error paths, rate limiting, User-Agent filtering, Kubernetes client configuration, and Gunicorn configuration with 95% branch coverage.
- Kubernetes integration tests using Kind to validate in-cluster OIDC discovery and JWKS reflection end-to-end.
- Automated release workflow with SBOM generation, provenance attestations, vulnerability scanning, and Cosign image signing.
- Security scanning workflow with CodeQL, Snyk, pip-audit, Semgrep, and SBOM/Grype analysis.
- Scheduled security rebuild workflow for daily base-image patching.
- Nightly Chainguard Python version monitoring with automated PR generation.
- Main-to-develop branch synchronization workflow.
- Dependabot configuration with grouped production and development dependency updates targeting `develop`.
- `pyproject.toml` as single source of truth for project version, dependencies, and tooling configuration.
- `tox.ini` for reproducible local and CI test execution with coverage gate.
- `Makefile` with standard development targets.

### Changed

- Migrated container base image from `python:3.12-slim-trixie` to Chainguard Python for reduced CVE surface and daily security updates.
- Container now runs as non-root UID 65532 (Chainguard default) with shell-independent Dockerfile.
- Canonical image registry changed to `ghcr.io/djr747/kube-oidc-issuer-reflector`.
- Replaced monolithic Docker build workflow with separated CI, release, security, and maintenance workflows.
- Pin all GitHub Actions to immutable commit SHAs.

### Fixed

- Readiness probe now verifies Kubernetes API connectivity and OIDC endpoint accessibility rather than always returning 200.
- Liveness probe no longer attempts Kubernetes API calls that could cause unnecessary pod restarts during transient control-plane issues.
