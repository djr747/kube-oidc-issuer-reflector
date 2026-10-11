# Multi-stage build on Red Hat UBI9 Python 3.14.
#
# UBI is free for production use (self-supported) on an RHEL 9 base that Red Hat
# supports to 2032, with security patching driven by the RHEL security team.
# We pin to an immutable build tag (not a floating tag) so image rebuilds are
# reproducible; bump the tag when a newer patched build is published.
FROM registry.access.redhat.com/ubi9/python-314:1-1787618080 AS builder

# UBI runs as the unprivileged app-root user (UID 1001) by default; keep the
# build rootless and put build scratch in /tmp.
WORKDIR /tmp/build

# Install the application and its production dependencies from pyproject.toml.
COPY pyproject.toml ./
COPY app ./app

# Install dependencies from wheels only. The UBI base is glibc and Python 3.14,
# and PyYAML publishes cp314 manylinux wheels, so no source build is required.
RUN ["python", "-m", "pip", "install", "--no-cache-dir", "--only-binary", ":all:", "."]

# Final stage - the same pinned UBI9 Python 3.14 image.
FROM registry.access.redhat.com/ubi9/python-314:1-1787618080 AS final

LABEL org.opencontainers.image.title="kube-oidc-issuer-reflector" \
      org.opencontainers.image.description="A simple Python application for exposing Kubernetes' OIDC issuer metadata (discovery document and JWKS) anonymously outside the cluster." \
      org.opencontainers.image.source="https://github.com/djr747/kube-oidc-issuer-reflector" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="registry.access.redhat.com/ubi9/python-314:1-1787618080"

# Copy installed packages and their console scripts (gunicorn) from the builder.
COPY --from=builder --chown=1001:0 /opt/app-root/lib/python3.14/site-packages /opt/app-root/lib/python3.14/site-packages
COPY --from=builder --chown=1001:0 /opt/app-root/bin /opt/app-root/bin

# UBI's app-root home (/opt/app-root/src) is writable by the app user (UID 1001).
WORKDIR /opt/app-root/src
COPY --chown=1001:0 app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# UBI's default user is the unprivileged app-root user (UID 1001).
USER 1001

# UBI's default entrypoint is container-entrypoint; set python explicitly so the
# CMD below runs as a plain python module launch.
ENTRYPOINT ["python"]

# Health check uses python (no shell assumption).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD ["-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/livez', timeout=3)"]

EXPOSE 8080

CMD ["-m", "gunicorn", "--config", "app/gunicorn_config.py", "app.main:app"]
