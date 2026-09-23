# Repository instructions

## Chainguard base images

- Use mutable version tags for Chainguard base images so rebuilds receive security patches; do not pin them with `@sha256` digests.
- For the Python base image, use the `3` and `3-dev` tags for runtime and builder stages, respectively, and keep `org.opencontainers.image.base.name` aligned with the runtime tag.
- Before changing a Chainguard tag, verify that the exact tag is pullable in the project's GitHub Actions environment. Some version tags may require registry access that is not configured in CI.
