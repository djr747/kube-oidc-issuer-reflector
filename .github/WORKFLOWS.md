# GitHub Actions Workflows

| Workflow | Purpose |
| --- | --- |
| `ci.yml` | Formatting, linting, typing, 100% statement and branch coverage, manifest validation, architecture builds, Kind integration, and develop image publishing. |
| `release.yml` | Gated main-branch releases with SBOM, provenance, Snyk scan, Cosign signing, image tags, Git tag, and GitHub Release. |
| `security.yml` | CodeQL, pip-audit, Semgrep, and Trivy scans. |
| `scheduled-rebuild.yml` | Daily rebuild of mutable image tags from Chainguard latest. |
| `nightly-chainguard-python-version.yml` | Detects Python version changes in Chainguard latest and opens a develop PR. |
| `merge-main-to-develop.yml` | Fast-forwards approved main changes to develop. |

`SNYK_TOKEN` is required for release scanning. `SONAR_TOKEN` is optional; CI reports a notice and skips the SonarQube Cloud scan when it is not configured. The public-repository Codecov upload is non-blocking if the service is unavailable. Pull-request jobs never publish images and do not receive repository secrets from forks.
