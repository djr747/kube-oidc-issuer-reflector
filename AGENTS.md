# Repository instructions

## Chainguard base images

- Use mutable tags for Chainguard base images so rebuilds receive security patches; do not pin them with `@sha256` digests.
- For the Python base image, use the `3` and `3-dev` tags for runtime and builder stages, respectively, and keep `org.opencontainers.image.base.name` aligned with the runtime tag.
- Preserve the requested Chainguard tags. If the project's GitHub Actions environment cannot pull them, report the access failure and ask for registry access to be configured; do not substitute another tag.
