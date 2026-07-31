# Multi-stage build with Chainguard Python for minimal attack surface and daily security updates
# Chainguard images: ultra-minimal, zero CVEs, updated daily, SLSA Level 3 provenance
# Use -dev variant for builder (includes pip, build tools), minimal runtime for final stage
FROM cgr.dev/chainguard/python:latest-dev AS builder

# pip installs console scripts into the non-root user site directory.
ENV PATH="/home/nonroot/.local/bin:$PATH"

WORKDIR /build

# Copy source needed to install the local package.
COPY pyproject.toml ./
COPY app ./app

# Install dependencies (production only)
# Chainguard images have no shell - use exec form (JSON array) for RUN
RUN ["python", "-m", "pip", "install", "--no-cache-dir", "--upgrade", "pip", "setuptools", "wheel"]
RUN ["python", "-m", "pip", "install", "--no-cache-dir", "."]

# Final stage - Chainguard Python (minimal runtime, non-root by default)
FROM cgr.dev/chainguard/python:latest

LABEL org.opencontainers.image.title="kube-oidc-issuer-reflector" \
      org.opencontainers.image.description="A simple Python application for exposing Kubernetes' OIDC issuer metadata (discovery document and JWKS) anonymously outside the cluster." \
      org.opencontainers.image.source="https://github.com/djr747/kube-oidc-issuer-reflector" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="cgr.dev/chainguard/python:latest"

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
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/readyz', timeout=3)"]

EXPOSE 8080

# Chainguard Python base image sets ENTRYPOINT to python automatically
CMD ["-m", "gunicorn", "--config", "app/gunicorn_config.py", "app.main:app"]
