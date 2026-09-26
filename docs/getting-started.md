# Getting Started

## Prerequisites

- A Kubernetes cluster whose API server service-account issuer can be configured.
- `kubectl` access with permission to create cluster and namespaced resources.
- An HTTPS hostname for the issuer, reachable by its intended token validators and stored in `OIDC_ISSUER_FQDN` without a scheme or path.
- A maintained Gateway API or Ingress implementation with an HTTPS listener on the selected public or private network.
- `envsubst` for rendering the optional route manifests.

For example:

```bash
export OIDC_ISSUER_FQDN=oidc.example.com
```

DNS must direct this hostname to the selected gateway, ingress controller, API gateway, or WAF. It can use public DNS, private DNS, or split-horizon DNS depending on where token validation happens. The application itself does not terminate TLS.

## Configure the Kubernetes issuer

Configure the API server so newly issued service-account tokens use the chosen issuer URL and the discovery document points token validators back to this service:

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

The reflector reads the source documents through the in-cluster Kubernetes API, so it does not require a CoreDNS override for the issuer hostname. Token validators need to resolve and reach that hostname; internal validators can use the private DNS setup described below.

## DNS and access patterns

Choose reachability based on where the **token validator** runs. A workload running inside Kubernetes may present its token to an internet-based identity provider; that provider still needs its own network access to the issuer's discovery and JWKS URLs. Kubernetes requires an HTTPS issuer URL and supports configuring the advertised JWKS URI separately. See [Kubernetes service-account issuer discovery](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#service-account-issuer-discovery).

### Public and internal access with split-horizon DNS

Use split-horizon DNS when both public and private validators should use one issuer while taking different network paths:

| Resolver used by the validator | Name queried | Destination |
| --- | --- | --- |
| Public DNS | `oidc.example.com` | Public HTTPS gateway or load balancer. |
| Corporate or cluster DNS | `oidc.example.com` | Private HTTPS gateway or load balancer. |

Keep `https://oidc.example.com` as the issuer in the API server settings, token `iss` claim, discovery document, and validator trust configuration. Keep `https://oidc.example.com/openid/v1/jwks` as the advertised JWKS URI for this example. Both routes must serve documents from the same issuing cluster. Using another hostname for internal discovery can cause issuer mismatch errors with standard discovery clients; DNS lets you preserve the canonical URL. See [OIDC discovery validation](https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderConfigurationValidation).

Configure the private DNS record in your organization's resolver or private DNS zone, and ensure cluster DNS forwards or resolves that name through it when in-cluster validators need the private route. Configure each HTTPS listener for the same hostname with a certificate its callers trust. This can avoid sending internal requests through an internet-facing load balancer when a private path is available. DNS records and gateway listeners are managed separately from this chart; it does not provision DNS or load balancers for them.

Split-horizon DNS is optional: if internal validators can already reach the public route, they can use it. The reflector's upstream calls continue to use the in-cluster Kubernetes API regardless of the DNS view.

### Private-only deployment

A private issuer is useful for internal APIs validating workload tokens, services on a corporate network, and services in other clusters connected through a VPN or private interconnect. It provides discovery and signing keys to those validators without giving them Kubernetes API credentials.

Use a private DNS record and an internal HTTPS Ingress or Gateway, with no public listener or public address record for the issuer. The Helm workload can remain a `ClusterIP` Service. Enable the chart's Ingress using the class backed by your internal controller, or enable its Gateway route and reference an existing private Gateway. Internal load-balancer settings are specific to your infrastructure and belong in that controller or Gateway configuration. Restrict access using your network and gateway policies. For private CA certificates, configure every validator to trust the issuing CA.

The same HTTPS issuer and JWKS rules apply. An internal Service name or plain HTTP URL does not automatically replace the issuer URL. Check DNS, certificate trust, discovery metadata, and JWKS retrieval from every network where a validator runs, including any configured `User-Agent` filter.

If a validator can already read the documents directly from the Kubernetes API and reach the advertised JWKS URI, it may not need the reflector. A private-only route cannot serve an internet-based validator unless that validator supports connectivity to your private network.

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

1. Review the image in `deploy/deploy.yaml`. Its release tag is synchronized from `project.version` in `pyproject.toml`. For production, pin the image digest if you require immutable deployment inputs.

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
| `OIDC_DOCUMENT_CACHE_TTL_SECONDS` | `30` | How long each validated discovery or JWKS document is reused before refreshing from the Kubernetes API. Set to `0` to disable fresh reuse. |
| `OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS` | `300` | Extra time beyond the freshness TTL that the last document may be served if an upstream fetch fails, including API throttling. Set to `0` to disable stale fallback. |
| `OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS` | `5` | After a failed refresh with eligible stale data, how long to wait before retrying the Kubernetes API for that document. |
| `OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES` | `1048576` | Maximum size of each document retained in the in-memory cache. Larger valid responses are served but not cached. |
| `LOG_LEVEL` | `INFO` | Gunicorn application and access log level. |
| `GUNICORN_PROCESSES` | `2` | Worker process count. Each worker has independent in-memory rate-limit state. |
| `GUNICORN_THREADS` | `4` | Threads per worker. |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn worker timeout in seconds. |

The cache is in-memory and local to each worker. It reduces API requests after each worker has loaded both documents and can keep endpoints available briefly through Kubernetes API errors or throttling. After a failed refresh, a short retry backoff prevents each incoming request from immediately repeating the same upstream call. It is not a shared cache across workers or replicas. Stale JWKS can temporarily omit a newly rotated signing key, so keep the stale window limited to the outage tolerance you need.

## Install with Helm

The released Helm chart installs the same secured workload and can optionally create an Ingress or Gateway API `HTTPRoute`. It does not install an ingress controller, Gateway, or Gateway API CRDs. Install a specific release into its own namespace without creating a public route:

```bash
helm upgrade --install kube-oidc-issuer-reflector \
  oci://ghcr.io/djr747/helm-charts/kube-oidc-issuer-reflector \
  --version X.Y.Z \
  --namespace kube-oidc-issuer-reflector --create-namespace
```

For local development, replace the OCI reference and version with `./charts/kube-oidc-issuer-reflector` from a repository checkout, and override `image.repository` and `image.tag` to select your built candidate image. The unpackaged development chart requires an explicit `image.tag`. See [Release Process](RELEASE.md#consuming-the-helm-chart) for package access and release details.

To create an Ingress, set `ingress.enabled=true`, `ingress.host` to `OIDC_ISSUER_FQDN`, and configure `ingress.additionalHosts` for other hostnames, `ingress.pathType`, `ingress.className`, TLS settings, and any controller or cert-manager annotations in a values file. To create a Gateway API route instead, set `gateway.enabled=true`, `gateway.name`, `gateway.namespace`, `gateway.sectionName`, and `gateway.host` to match an existing HTTPS listener. Enable only one route type.

The chart exposes every application environment setting in named values. Set `config.defaultRateLimit`, `config.allowedUserAgent`, `config.kubernetesRequestTimeoutSeconds`, `config.logLevel`, and the three `config.gunicorn*` values for application behavior. Tune the four `oidcDocumentCache.*` values for cache freshness, stale fallback, API retry backoff, and maximum document size. Set `livenessProbe` and `readinessProbe` to customize probe timing and endpoints. An empty `config.allowedUserAgent` leaves the filter disabled. Use `extraEnv` for additional container variables not defined by the app.

The chart defaults `serviceAccount.create` and `rbac.create` to `true`. This creates a dedicated ServiceAccount and binds it to the built-in `system:service-account-issuer-discovery` role, making the chart self-contained and suitable for clusters that require workloads to use dedicated ServiceAccounts. Kubernetes RBAC defaults also bind this role to the `system:serviceaccounts` group, so the chart's explicit binding is redundant when that default is present. Set `rbac.create=false` if your cluster already provides the needed permission. If your platform manages the dedicated ServiceAccount separately, set `serviceAccount.create=false` and provide `serviceAccount.name`; the RBAC binding can still be independently enabled or disabled. Keep `serviceAccount.automount=true` because the application uses the mounted token to call the Kubernetes API.

## External caller identity and rate limiting

This service supports OIDC consumers on public or private networks. Workloads that can read the documents directly from the Kubernetes API and reach the advertised JWKS URI may not need the reflector. Requests through a gateway are expected to pass through a controlled Ingress, Gateway API implementation, API gateway, or WAF; apply the same forwarding-header rules to a private gateway.

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

The manifests include a binding from the deployment's ServiceAccount to Kubernetes' built-in `system:service-account-issuer-discovery` ClusterRole. Stock RBAC configurations also bind this role to the `system:serviceaccounts` group, so a separate application binding is not required when that default binding remains in place. Include the ServiceAccount's groups when testing through impersonation; `--as` alone does not add them:

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
