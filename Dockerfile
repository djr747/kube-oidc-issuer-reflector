# Multi-stage build with Chainguard Python for a minimal attack surface.
# Floating major-version tags pick up new Python 3 patch releases.
# Use -dev variant for builder (includes pip, build tools), minimal runtime for final stage
FROM cgr.dev/chainguard/python:3-dev AS builder

# pip installs console scripts into the non-root user site directory.
ENV PATH="/home/nonroot/.local/bin:$PATH"

# Create the build directory as the existing non-root Chainguard user. This
# keeps both build and runtime stages rootless while allowing package metadata.
USER 65532
WORKDIR /home/nonroot
RUN ["mkdir", "-p", "build"]
WORKDIR /home/nonroot/build

# Copy the locked dependencies. Application source is copied directly into
# the final image and therefore does not need to be installed as a package.
COPY --chown=65532:65532 requirements.lock ./

# Install the hashed production dependency set from wheels only.
# Chainguard images have no shell - use exec form (JSON array) for RUN
RUN ["python", "-m", "pip", "install", "--no-cache-dir", "--only-binary", ":all:", "--require-hashes", "--requirement", "requirements.lock"]

# Final stage - Chainguard Python (minimal runtime, non-root by default)
FROM cgr.dev/chainguard/python:3

LABEL org.opencontainers.image.title="kube-oidc-issuer-reflector" \
      org.opencontainers.image.description="A simple Python application for exposing Kubernetes' OIDC issuer metadata (discovery document and JWKS) anonymously outside the cluster." \
      org.opencontainers.image.source="https://github.com/djr747/kube-oidc-issuer-reflector" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="cgr.dev/chainguard/python:3"

# Copy installed packages from builder
# Chainguard Python uses /home/nonroot/.local for user site-packages
COPY --from=builder --chown=65532:65532 /home/nonroot/.local /home/nonroot/.local

# Set environment variables
ENV PATH="/home/nonroot/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app
COPY --chown=65532:65532 app ./app
COPY --chown=65532:65532 pyproject.toml ./

# Chainguard images are already non-root (UID 65532)
USER 65532

# Health check - Chainguard images have no shell, use python
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/livez', timeout=3)"]

EXPOSE 8080

# Chainguard Python base image sets ENTRYPOINT to python automatically
CMD ["-m", "gunicorn", "--config", "app/gunicorn_config.py", "app.main:app"]
