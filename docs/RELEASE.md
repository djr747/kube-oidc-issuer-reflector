# Release Process

`pyproject.toml` is the single version source of truth. Every successful CI run on `main` starts the release workflow, so merge to `main` only when the version and changelog are ready for a release and the corresponding `vX.Y.Z` tag does not already exist.

1. Update `project.version` in `pyproject.toml` and add a matching section to `CHANGELOG.md` on `develop`.
2. Merge the reviewed pull request into `main` after all required checks pass.
3. The release workflow validates SemVer and the changelog, builds and scans the multi-architecture image, generates an SPDX SBOM and provenance, signs the image with keyless Cosign, then creates the Git tag and GitHub Release.

The Git tag and GitHub Release are named `vX.Y.Z`. Container image tags are `X.Y.Z`, `X.Y`, `X`, and `latest`. Pin the full `X.Y.Z` image tag or, preferably, its digest for reproducible production deployments.
