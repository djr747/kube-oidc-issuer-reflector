# Release Process

`pyproject.toml` is the single version source of truth. Releases are made only from a successful CI run on `main`.

1. Update `project.version` in `pyproject.toml` and add a matching section to `CHANGELOG.md` on `develop`.
2. Merge the reviewed pull request into `main` after all required checks pass.
3. The release workflow validates SemVer and the changelog, builds and scans the multi-architecture image, generates an SPDX SBOM and provenance, signs the image with keyless Cosign, then creates the Git tag and GitHub Release.

Release tags are `X.Y.Z`, `X.Y`, `X`, and `latest`. Pin an exact version tag or digest for reproducible production deployments.

The initial automated release is `v1.0.0`.
