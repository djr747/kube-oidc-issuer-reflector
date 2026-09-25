# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.1.2] - 2026-09-22

### Changed

- Use Chainguard's public floating `latest` and `latest-dev` tags so scheduled rebuilds can pick up base-image updates without digest changes.
- Use static route paths in debug request logs instead of logging request-derived values, preventing log injection.

## [1.1.1] - 2026-09-20

### Changed

- Updated `docker/login-action` to 4.6.0 across release and scheduled rebuild workflows.
- Updated all CodeQL actions to 4.38.0 as one synchronized set.

### Fixed

- Validated the matching changelog section before publishing any image tags and limited generated GitHub release notes to that version.
- Added complete unit coverage for release-note extraction, including missing, duplicate, and empty sections.

## [1.1.0] - 2026-09-20

### Changed

- Added bounded Kubernetes API requests and minimum schema validation for discovery and JWKS responses.
- Made access logging and application rate limiting consistently use the external caller at the start of the edge-normalized `X-Forwarded-For` chain.
- Documented the ingress/WAF header-normalization boundary and multi-hop caller selection.
- Raised enforced branch coverage to 100% and added single-hop, multi-hop, malformed-header, IPv4, and IPv6 caller tests.
- Removed coverage exclusion pragmas; the 100% gate now measures every application statement and branch.
- Separated edge routing from the workload and added controller-neutral Ingress and Gateway API options.
- Updated maintained Python dependencies and removed the unused CSRF extension.
- Hardened rolling updates with a PodDisruptionBudget and a versioned deployment image.
- Updated CI security tooling and made optional SonarQube Cloud analysis conditional on its secret.
- Reconciled deployment, proxy identity, Gateway API, Ingress, cert-manager, workflow, and release documentation with the implemented behavior and current upstream guidance.

### Fixed

- Removed ineffective namespaced RBAC rules for Kubernetes non-resource discovery URLs.
- Closed Kubernetes API clients after each request and stopped swallowing kubeconfig errors.
- Repaired the release workflow startup failure and replaced the unchecked Cosign download.
- Corrected the nightly Python-version comparison and synchronized all version-specific configuration.
- Prevented debug logs from recording all request headers.
- Made access-log `remote_ip` use the external caller while retaining the raw forwarded chain separately.
- Removed Gunicorn's wildcard trust for forwarding metadata from arbitrary peers.
- Fixed non-root container builds against current Chainguard Python images.
- Fixed Kind integration deployment by removing a multi-resource server dry run that could not persist its Namespace.
- Added a bounded memory-backed `/tmp` volume required by Gunicorn with a read-only root filesystem.
- Closed the real Kubernetes `ApiClient` rather than generated API wrappers and disabled Gunicorn's unused writable control socket.
- Corrected integration-test impersonation groups, attached disposable curl probes, and surfaced kubectl diagnostics.
- Updated non-resource authorization checks for current kubectl syntax and eliminated probe-pod deletion races.
- Corrected the optional Cloudflare issuer to use API-token names and fields without the API-key-only account email.
- Made the local Kind runner use the Python interpreter selected by the Makefile instead of assuming a `python` executable is on `PATH`.
- Made release publication a downstream job of the successful `main` CI run, eliminating privileged `workflow_run` checkout while retaining exact-revision verification.
- Removed the unused manifest-path argument from the integration renderer so CI cannot redirect it to an arbitrary file.
- Initialized Flask CSRF protection so any future state-changing endpoint is protected by default; the current public OIDC endpoints remain read-only.
- Added a portable, hashed dependency lock and restricted CI and image dependency installation to published wheels.
- Made the image and CI consume hashed requirements exported from `uv.lock` and removed redundant local-project dependency resolution.
- Bound the reflector ServiceAccount explicitly to Kubernetes' OIDC discovery ClusterRole instead of relying on the cluster-wide default binding.

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
