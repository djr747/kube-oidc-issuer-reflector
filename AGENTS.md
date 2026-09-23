# Repository instructions

## Chainguard base images

- Use mutable tags for Chainguard base images so rebuilds receive security patches; do not pin them with `@sha256` digests.
- For this public project, use the publicly pullable `latest` and `latest-dev` Python tags for runtime and builder stages, respectively, and keep `org.opencontainers.image.base.name` aligned with the runtime tag.
- Before changing a Chainguard tag, verify that the exact tag is pullable in the project's GitHub Actions environment. Version-specific tags may require registry access that is not configured in CI.
