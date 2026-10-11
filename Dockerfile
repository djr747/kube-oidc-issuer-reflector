# Multi-stage build on Docker Hardened Images (DHI) Python 3.14 (Debian 13).
#
# DHI images are built, signed and patched by Docker: the base is rebuilt on
# a schedule from Docker's own Debian packages (versions carry a `+dhiN`
# suffix), so OS security fixes and Python security updates land in new
# pushes of the tag. The tag is therefore floating on the Python 3.14 patch
# line (3.14-debian13 tracks any 3.14.x): every `docker build` pulls the
# newest patched base automatically, with no re-bake/re-pin cycle. (The
# trade-off vs a digest-pinned tag is build-to-build reproducibility; the
# nightly security scan re-checks whatever base the build actually used.)
#
# Pulling requires a DHI registry login (`docker login dhi.io`); CI supplies
# it from the DHI_USERNAME / DHI_PASSWORD repository secrets. The free tier
# is pull-only and self-supported; SLA-backed updates and FIPS/STIG variants
# are part of the paid Hardened Images tier.
FROM dhi.io/python:3.14-debian13 AS builder

# DHI runtime images deliberately ship without a shell and without a package
# manager (apt is stripped from the runtime), so every build step below is an
# exec-form invocation and nothing may invoke sh.
WORKDIR /build
COPY pyproject.toml ./
COPY app ./app

# Install dependencies from wheels only. The DHI base is glibc and Python
# 3.14, and PyYAML publishes cp314 manylinux wheels, so no source build is
# required.
RUN ["python3", "-m", "pip", "install", "--no-cache-dir", "--only-binary", ":all:", "."]

# Final stage - the same DHI Python 3.14 (Debian 13) image.
FROM dhi.io/python:3.14-debian13 AS final

LABEL org.opencontainers.image.title="kube-oidc-issuer-reflector" \
      org.opencontainers.image.description="A simple Python application for exposing Kubernetes' OIDC issuer metadata (discovery document and JWKS) anonymously outside the cluster." \
      org.opencontainers.image.source="https://github.com/djr747/kube-oidc-issuer-reflector" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="dhi.io/python:3.14-debian13"

# Copy the installed packages from the builder. This is a Debian build of
# Python, so system `pip install` lands in /usr/lib/python3/dist-packages
# (the Debian default), which /usr/lib/python3.14/site-packages/
# dhi-distpackages.pth already puts on sys.path in both stages. Copying
# site-packages instead would copy an empty directory and ship an image
# without gunicorn. The app entrypoint is `python3 -m gunicorn`, so the
# console scripts in /usr/local/bin are not needed in the final stage.
COPY --from=builder --chown=65532:65532 /usr/lib/python3/dist-packages /usr/lib/python3/dist-packages

WORKDIR /app
COPY --chown=65532:65532 app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# DHI ships the unprivileged nonroot user (UID 65532) and no default user;
# run as nonroot. Gunicorn logs to stdout and its control socket is disabled
# in app/gunicorn_config.py, so the read-only root filesystem (set by the
# Helm chart) needs no writable paths.
USER 65532

# The image ships no shell and no entrypoint; set python3 explicitly so the
# CMD below runs as a plain python module launch.
ENTRYPOINT ["python3"]

# Health check uses python3 (no shell assumption).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD ["-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/livez', timeout=3)"]

EXPOSE 8080

CMD ["-m", "gunicorn", "--config", "app/gunicorn_config.py", "app.main:app"]
