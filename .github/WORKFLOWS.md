# GitHub Actions Workflows

| Workflow | Purpose |
| --- | --- |
| `ci.yml` | Formatting, linting, typing, 100% statement and branch coverage, manifest validation, architecture builds, Kind integration, develop image publishing, and gated main-branch releases with SBOM, provenance, Snyk scanning, Cosign signing, image tags, a Git tag, and a GitHub Release. |
| `security.yml` | CodeQL, pip-audit, Semgrep, and Trivy scans. |
| `scheduled-rebuild.yml` | Daily no-cache rebuild of mutable image tags from the audited, digest-pinned `main` sources. Dependabot proposes weekly base-image digest updates. |
| `nightly-chainguard-python-version.yml` | Detects Python version changes in Chainguard latest and opens a develop PR. |
| `merge-main-to-develop.yml` | Fast-forwards approved main changes to develop. |

`SNYK_TOKEN` is required for release scanning. `SONAR_TOKEN` is optional; CI reports a notice and skips the SonarQube Cloud scan when it is not configured. The public-repository Codecov upload is non-blocking if the service is unavailable. Pull-request jobs never publish images and do not receive repository secrets from forks.
