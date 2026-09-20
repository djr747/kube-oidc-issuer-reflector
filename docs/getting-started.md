# Getting Started

## Prerequisites

- A Kubernetes cluster whose API server service-account issuer can be configured.
- `kubectl` access with permission to create cluster and namespaced resources.
- A public HTTPS hostname for the issuer, stored in `OIDC_ISSUER_FQDN` without a scheme or path.
- A maintained Gateway API or Ingress implementation at the public edge.
- `envsubst` for rendering the optional route manifests.

For example:

```bash
export OIDC_ISSUER_FQDN=oidc.example.com
```

Public DNS must direct this hostname to the selected gateway, ingress controller, API gateway, or WAF. The application itself does not terminate TLS.

## Configure the Kubernetes issuer

Configure the API server so newly issued service-account tokens use the public issuer URL and the discovery document points external token validators back to this service:

```text
--service-account-issuer=https://oidc.example.com
--service-account-jwks-uri=https://oidc.example.com/openid/v1/jwks
```

Replace `oidc.example.com` with the value of `OIDC_ISSUER_FQDN`. Both values must use HTTPS. How these settings are changed is distribution-specific; on a managed Kubernetes service, confirm that the provider supports a configurable service-account issuer before continuing.

Changing the issuer affects the `iss` claim of newly created service-account tokens. Plan the change using the Kubernetes guidance for issuer migration if existing tokens or relying parties must continue to work during a transition.

### MicroK8s example

For MicroK8s, edit `/var/snap/microk8s/current/args/kube-apiserver`, add the two API server arguments above, and restart MicroK8s:

```bash
sudo microk8s stop
sudo microk8s start
microk8s status --wait-ready
```

This repository does not require a CoreDNS override. The reflector reads the source documents through the in-cluster Kubernetes API; only external token consumers need to resolve the public issuer hostname.

## Choose a public route

Kubernetes Ingress remains supported and stable, but its API is frozen. The ingress-nginx controller was retired in March 2026 and should not be selected for a new installation. This repository provides two controller-neutral route manifests:

- `deploy/optional-gateway-api.yaml` is the preferred Gateway API `HTTPRoute` for Traefik, Envoy Gateway, Istio, Kong, and other conformant implementations.
- `deploy/optional-ingress.yaml` is a standard Kubernetes `Ingress` for maintained implementations that still support that API.

The manifests expose only the discovery and JWKS paths. The core workload in `deploy/deploy.yaml` does not select or install an edge implementation.

### Traefik Gateway API example

Skip this section if the cluster already has a Gateway API implementation. Install the current standard Gateway API CRDs:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.2/standard-install.yaml
```

Configure Traefik's Gateway provider and an HTTPS listener in its Helm values. Because the `HTTPRoute` is in a different namespace from the example Gateway, the listener must allow routes from other namespaces:

```yaml
providers:
  kubernetesGateway:
    enabled: true
gateway:
  listeners:
    websecure:
      port: 443
      protocol: HTTPS
      namespacePolicy:
        from: All
      mode: Terminate
      certificateRefs:
        - kind: Secret
          name: oidc-issuer-tls
          group: ""
```

Save the values as `traefik-values.yaml`, then install or upgrade Traefik:

```bash
helm repo add traefik https://traefik.github.io/charts
helm repo update
helm upgrade --install traefik traefik/traefik \
  --namespace traefik --create-namespace --wait \
  --values traefik-values.yaml
```

The referenced TLS Secret must exist in the Gateway namespace before this installation. Use a certificate issued by your organization, cert-manager, or Traefik's ACME integration. Restrict allowed route namespaces more tightly in a separately managed Gateway when your implementation supports the policy you require.

Confirm the names created by your installation instead of assuming them:

```bash
kubectl get gatewayclass
kubectl get gateway -A
```

## Optional: install cert-manager

The included Ingress example can request a certificate from cert-manager. Install the current pinned OCI chart and its CRDs if cert-manager is not already managed by the cluster:

```bash
helm install cert-manager oci://quay.io/jetstack/charts/cert-manager \
  --namespace cert-manager --create-namespace \
  --version v1.21.2 \
  --set crds.enabled=true
kubectl get pods -n cert-manager
```

Before upgrading the pinned version, review cert-manager's supported releases and upgrade notes.

The optional Cloudflare issuer uses a scoped API token. Give the token `Zone:DNS:Edit` and `Zone:Zone:Read` permissions for only the required zones where possible, then set:

```bash
export CLOUDFLARE_API_TOKEN='replace-with-token'
export CERT_ISSUER_EMAIL='platform@example.com'
```

Treat rendered output and shell history as sensitive because the template contains the token. Prefer creating the Secret with your normal secret-management system in production.

## Deploy the application

1. Review the image in `deploy/deploy.yaml`. It is pinned to the `1.1.0` release tag. For production, pin the image digest if you require immutable deployment inputs.

2. Apply the controller-independent workload:

   ```bash
   kubectl apply -f deploy/deploy.yaml
   kubectl -n kube-oidc-issuer-reflector rollout status \
     deployment/kube-oidc-issuer-reflector --timeout=180s
   ```

3. Choose exactly one route.

   For Gateway API, reference an existing HTTPS listener:

   ```bash
   export GATEWAY_NAME="$(kubectl get gateway -n traefik -o jsonpath='{.items[0].metadata.name}')"
   export GATEWAY_NAMESPACE=traefik
   export GATEWAY_LISTENER_NAME=websecure
   envsubst '$OIDC_ISSUER_FQDN $GATEWAY_NAME $GATEWAY_NAMESPACE $GATEWAY_LISTENER_NAME' \
     < deploy/optional-gateway-api.yaml | kubectl apply -f -
   ```

   TLS is owned by the parent Gateway listener; the `HTTPRoute` does not create a certificate.

   Or, for a maintained standard Ingress implementation, first create the optional Cloudflare issuer when required:

   ```bash
   envsubst '$CLOUDFLARE_API_TOKEN $CERT_ISSUER_EMAIL' \
     < deploy/optional-ingress-cert-issuer.yaml | kubectl apply -f -

   export INGRESS_CLASS_NAME=traefik
   export CLUSTER_ISSUER_NAME=cloudflare-issuer
   envsubst '$OIDC_ISSUER_FQDN $INGRESS_CLASS_NAME $CLUSTER_ISSUER_NAME' \
     < deploy/optional-ingress.yaml | kubectl apply -f -
   ```

   If TLS is managed outside cert-manager, remove the `cert-manager.io/cluster-issuer` annotation from your rendered Ingress and use the TLS Secret supplied by that system.

4. Confirm that the route was accepted and has an address:

   ```bash
   kubectl get pods,service -n kube-oidc-issuer-reflector
   kubectl describe httproute kube-oidc-issuer-reflector \
     -n kube-oidc-issuer-reflector
   kubectl describe ingress kube-oidc-issuer-reflector \
     -n kube-oidc-issuer-reflector
   ```

   Run only the `describe` command for the route type you selected.

5. Verify both public responses:

   ```bash
   curl --fail --show-error "https://${OIDC_ISSUER_FQDN}/.well-known/openid-configuration"
   curl --fail --show-error "https://${OIDC_ISSUER_FQDN}/openid/v1/jwks"
   ```

## Configuration

The deployment uses the application defaults. Add environment variables to the container spec only when an override is needed.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEFAULT_RATE_LIMIT` | `10 per second` | Per-worker, per-client limit for the two reflected endpoints. |
| `ALLOWED_USER_AGENT` | unset | When set, require an exact `User-Agent` match. This is filtering, not authentication. |
| `KUBERNETES_REQUEST_TIMEOUT_SECONDS` | `5` | Positive client-side timeout, in seconds, for each Kubernetes API request. |
| `LOG_LEVEL` | `INFO` | Gunicorn application and access log level. |
| `GUNICORN_PROCESSES` | `2` | Worker process count. Each worker has independent in-memory rate-limit state. |
| `GUNICORN_THREADS` | `4` | Threads per worker. |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn worker timeout in seconds. |

## External caller identity and rate limiting

This service is intended for external OIDC consumers. Workloads in the cluster can call the Kubernetes API service directly and do not need the reflector. Public requests are expected to pass through a controlled ingress, Gateway API implementation, API gateway, or WAF.

The public edge must remove caller-supplied forwarding headers and create a normalized `X-Forwarded-For` chain. The application uses the first (left-most) value as the external caller, regardless of how many trusted edge components follow it:

| Public path | Normalized `X-Forwarded-For` | Address used |
| --- | --- | --- |
| Client → gateway | `198.51.100.20` | `198.51.100.20` |
| Client → WAF → gateway | `198.51.100.20, 192.0.2.45` | `198.51.100.20` |
| Client → load balancer → WAF → gateway | `198.51.100.20, 192.0.2.30, 192.0.2.45` | `198.51.100.20` |

That one resolved address is used for both `remote_ip` in the JSON access log and the application rate-limit key. This behavior does not depend on the proxy product. If `X-Forwarded-For` is missing or its first value is not a valid IPv4 or IPv6 address, the application falls back to the socket peer. The log's `forwarded_for` field preserves the raw header for diagnosis.

Do not expose a path that bypasses the edge normalization. If untrusted clients can supply the header unchanged, they can choose the logged identity and evade per-client limiting. Configure the outermost public edge to discard inbound forwarding headers; each later trusted proxy may append its peer. If a product emits only `Forwarded`, `X-Real-IP`, or a vendor-specific header, translate the verified client address into `X-Forwarded-For` before forwarding to this service.

The limiter uses in-memory state independently in every Gunicorn worker and replica. It protects each process from a single resolved client, but it is not a cluster-wide quota. Enforce a globally consistent limit at the gateway or WAF when that is required.

## Verify Kubernetes authorization

Kubernetes normally binds the `system:service-account-issuer-discovery` ClusterRole to the `system:serviceaccounts` group. Include the ServiceAccount's groups when testing through impersonation; `--as` alone does not add them:

```bash
for path in /.well-known/openid-configuration /openid/v1/jwks; do
  kubectl auth can-i get "$path" \
    --as=system:serviceaccount:kube-oidc-issuer-reflector:kube-oidc-issuer-reflector \
    --as-group=system:serviceaccounts \
    --as-group=system:serviceaccounts:kube-oidc-issuer-reflector \
    --as-group=system:authenticated
done
```

Both checks should return `yes`. If they do not, see [Troubleshooting](troubleshooting.md).

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution requirements.
