# Repository guidance for coding agents

Read this file before changing this repository. Follow the user's current instructions when they are more specific.

## Git and release boundaries

- Work on the existing `develop` branch. Before editing, confirm it is checked out. Do not create, switch to, push, or use a Codex-owned branch. If `develop` cannot be used safely, stop and ask.
- Do not commit or push `develop` unless the user explicitly requests it. Create or update a pull request from `develop` only when explicitly requested.
- Never merge, auto-merge, close, or enable auto-merge on a pull request. Prepare it for the user to merge manually.
- Before changing a third-party version or image tag, check the vendor's official documentation for availability and access requirements. Do not silently substitute a different value.
- `pyproject.toml` is the sole application version source. Use SemVer: new compatible features belong in a minor release; compatible fixes belong in a patch release. Add the matching `CHANGELOG.md` section, then run `scripts/sync_release_version.py` with Python 3.14 to update `uv.lock` and `deploy/deploy.yaml`. Search for stale version-specific examples afterward.
- The chart's committed `Chart.yaml` contains development metadata. CI packages the chart with the application version as both chart version and `appVersion`; the default chart image tag follows that version. Do not manually maintain a second release number in chart source. See `docs/RELEASE.md`.

## What the service does

- The reflector serves the Kubernetes API server's service-account OIDC discovery document and JWKS at `/.well-known/openid-configuration` and `/openid/v1/jwks`. It does not issue tokens or rewrite the issuer.
- For an externally reachable self-managed issuer, document the API server's service-account issuer and public JWKS URI settings. `--oidc-issuer-url` configures Kubernetes to authenticate incoming OIDC clients and is a different feature.
- Entra federated credential issuer and subject must match the workload's projected service-account token. The workload ServiceAccount is distinct from the reflector's account. The credential audience must match the token audience; do not present one audience string as universal for every federation flow.
- `ALLOWED_USER_AGENT` is optional and requires an exact `User-Agent` match when set. It filters requests but is not authentication. Include the configured header when documenting or probing the public OIDC paths.
- OIDC documents are validated and cached in each worker independently. Cache freshness, stale-on-error time, retry backoff, and document size are configured with `OIDC_DOCUMENT_CACHE_*` settings. Do not describe this as a shared cache.

## Kubernetes and Helm

- Every pod uses a ServiceAccount, but a dedicated reflector ServiceAccount is optional. The application needs an automounted token to call the Kubernetes API. Stock Kubernetes RBAC binds `system:service-account-issuer-discovery` to all ServiceAccounts; a dedicated ClusterRoleBinding is optional when that binding remains in place. Namespaced Roles for fictional OIDC resources do not grant access to the discovery URLs.
- The Helm chart defaults to creating a dedicated ServiceAccount and binding. To use the namespace's `default` account, set `serviceAccount.create=false`, `serviceAccount.name=default`, and `rbac.create=false`; keep `serviceAccount.automount=true`. The settings are independent for environments with different RBAC policies.
- The chart exposes application settings, cache settings, deployment resources, probes, service-account/RBAC choices, and optional Ingress or Gateway API routing through `charts/kube-oidc-issuer-reflector/values.yaml`. Use released OCI charts for consumer examples and a local chart path only for development. Keep chart and image release versions aligned.
- Public routes need a maintained controller or Gateway and TLS configured separately. A certificate SAN validates the hostname; it does not set the discovery document's `issuer`. With a port-443-only perimeter, use a suitable DNS validation or certificate process instead of an HTTP-01 flow that needs port 80.

## Documentation and verification

- Do not put live cluster hostnames, addresses, or other user endpoints in examples. Use reserved example domains and placeholders. Preserve the user's architecture while checking claims against repository code and authoritative upstream documentation.
- Keep installation examples internally consistent: Helm values and command together, or all static resources together. Distinguish published release artifacts from unreleased local builds. General release instructions can use version placeholders; concrete versioned examples must be checked when the project version changes.
- `make all` runs local formatting, lint, type, and unit checks. `make test-helm` checks the packaged chart and configuration variants. For requested cluster integration verification, build the local `:ci` image and run `make test-integration` with Docker or a compatible Podman socket; Podman images may need the `localhost/` prefix in `IMAGE`. The Kind suite checks both static and Helm deployments for reflected documents, authorization, readiness, and stale cache behavior after API access is revoked. Keep the explicit test-context and issuer guards, and use test cluster names starting with `oidc-reflector-`. Report exactly which checks were run; unit coverage alone is not integration evidence.
- Treat the user's Kubernetes clusters as read-only for investigation unless a request authorizes a change. Select the requested context explicitly and do not copy observed endpoints into documentation.
