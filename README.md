# Kubernetes OIDC Issuer Reflector

[![CI](https://github.com/djr747/kube-oidc-issuer-reflector/actions/workflows/ci.yml/badge.svg)](https://github.com/djr747/kube-oidc-issuer-reflector/actions/workflows/ci.yml)
[![Security](https://github.com/djr747/kube-oidc-issuer-reflector/actions/workflows/security.yml/badge.svg)](https://github.com/djr747/kube-oidc-issuer-reflector/actions/workflows/security.yml)
[![Coverage](https://codecov.io/gh/djr747/kube-oidc-issuer-reflector/branch/main/graph/badge.svg)](https://codecov.io/gh/djr747/kube-oidc-issuer-reflector)

This service anonymously reflects the Kubernetes API server's OIDC discovery document and JWKS outside the cluster. It is intended for clusters whose service-account issuer must be reachable by external token consumers.

Only the two public OIDC endpoints are exposed:

- `/.well-known/openid-configuration`
- `/openid/v1/jwks`

The core deployment is independent of the public edge. Use the optional Gateway API `HTTPRoute` or standard Kubernetes `Ingress` with a maintained controller such as Traefik, Envoy Gateway, Istio, or Kong.

## Container Image

Release images are published to GitHub Container Registry:

```text
ghcr.io/djr747/kube-oidc-issuer-reflector:1.1.0
```

Use an exact release tag or digest in production. The mutable `latest` tag is rebuilt daily from `main`; `develop` is published after successful pushes to the `develop` branch.

## Getting Started

See [Getting Started](docs/getting-started.md) for cluster setup and deployment.

## Development

See [Development](docs/DEVELOPMENT.md) for Python 3.14 setup, local checks, coverage, and Kind integration tests.

## Releases

See [Release Process](docs/RELEASE.md). Full workflow details are in [.github/WORKFLOWS.md](.github/WORKFLOWS.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) and [GitHub Releases](https://github.com/djr747/kube-oidc-issuer-reflector/releases).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

[MIT](LICENSE)
