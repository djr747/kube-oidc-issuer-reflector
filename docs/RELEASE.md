# Release Process

`pyproject.toml` is the single source of truth for the application version. CI passes it to Helm when packaging, so the chart package version, chart `appVersion`, and default image tag are generated from the same value. `uv.lock` and the pinned image in `deploy/deploy.yaml` are derived files. Every successful CI run on `main` starts the release workflow, so merge to `main` only when the version and changelog are ready for a release and the corresponding `vX.Y.Z` tag does not already exist.

1. Update `project.version` in `pyproject.toml` and add a matching section to `CHANGELOG.md` on `develop`.
2. Run `python scripts/sync_release_version.py`. It regenerates `uv.lock` and updates the pinned image in `deploy/deploy.yaml` from `pyproject.toml`. The chart's committed `Chart.yaml` uses `0.0.0` development metadata and requires an explicit `image.tag` for local installs; CI injects the release version when packaging, and the image tag defaults to the chart's generated `appVersion`.
3. CI runs `helm lint`, tests chart configuration variants, packages it with the application version on pull requests and branch pushes, and checks the packaged chart metadata and rendered image tag. Kind integration tests exercise both the static deployment and that packaged chart. Develop image publication and main releases wait for these checks; the `main` release job reuses the tested archive.
4. Merge the reviewed pull request into `main` after all required checks pass.
5. The release workflow validates the application SemVer and changelog, builds and scans the multi-architecture image, generates an SPDX SBOM and provenance, signs the image with keyless Cosign, publishes the CI-built Helm archive to GHCR as an OCI artifact, then creates the Git tag and GitHub Release with that chart archive and SBOM attached.

The Git tag and GitHub Release are named `vX.Y.Z`. Container image tags are `X.Y.Z`, `X.Y`, `X`, and `latest`. Pin the full `X.Y.Z` image tag or, preferably, its digest for reproducible production deployments.

A push to `develop` runs CI and Security, including chart packaging and integration testing, and publishes the `develop` image after CI succeeds. It does not publish the versioned image, OCI chart, Git tag, or GitHub Release; those steps run only after a push to `main`. Scheduled workflows also keep their own schedule or manual trigger.

## Consuming the Helm chart

Install a released chart directly from the GitHub Container Registry OCI package:

```bash
helm upgrade --install kube-oidc-issuer-reflector \
  oci://ghcr.io/djr747/helm-charts/kube-oidc-issuer-reflector \
  --version X.Y.Z \
  --namespace kube-oidc-issuer-reflector --create-namespace
```

The same chart archive is attached to the GitHub Release. A newly published GHCR package is private by default, so after the first release make the package public in its GitHub package settings to allow anonymous pulls. Until then, authenticate Helm to `ghcr.io` with a GitHub token that can read packages, or download the chart archive from the public GitHub Release and install from the local `.tgz` file. Provide a values file with `--values your-values.yaml` to configure the image, application settings, service account and RBAC, resources, probes, or optional Ingress/Gateway API route. A public route also requires an appropriate controller or Gateway to already be installed. For local development, Helm can still install directly from `./charts/kube-oidc-issuer-reflector`.
