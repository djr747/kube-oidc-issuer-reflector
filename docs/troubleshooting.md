# Troubleshooting

## Readiness returns 503

The readiness endpoint verifies both Kubernetes issuer-discovery endpoints and validates their minimum JSON shape. Check the pod logs, then confirm the service account can read both non-resource URLs:

```bash
kubectl auth can-i get /.well-known/openid-configuration \
  --as=system:serviceaccount:kube-oidc-issuer-reflector:kube-oidc-issuer-reflector \
  --as-group=system:serviceaccounts \
  --as-group=system:serviceaccounts:kube-oidc-issuer-reflector \
  --as-group=system:authenticated
kubectl auth can-i get /openid/v1/jwks \
  --as=system:serviceaccount:kube-oidc-issuer-reflector:kube-oidc-issuer-reflector \
  --as-group=system:serviceaccounts \
  --as-group=system:serviceaccounts:kube-oidc-issuer-reflector \
  --as-group=system:authenticated
```

Both should return `yes` through the deployment's `kube-oidc-issuer-reflector-discovery` ClusterRoleBinding to Kubernetes' built-in `system:service-account-issuer-discovery` ClusterRole. The group flags matter because `kubectl --as` does not infer the groups normally attached to a ServiceAccount identity. Customized clusters can alter default RBAC, so inspect the ClusterRole and ClusterRoleBinding if either answer is `no`.

Also confirm the API server has valid HTTPS `--service-account-issuer` and `--service-account-jwks-uri` values.

If the API server is slow but healthy, increase `KUBERNETES_REQUEST_TIMEOUT_SECONDS` from its five-second default. The readiness probe performs two sequential API calls, so keep its timeout above twice the application timeout to prevent overlapping requests.

## Public discovery works but tokens do not validate

Compare the token's `iss` claim with the discovery document's `issuer` value exactly, including scheme and path. Then confirm `jwks_uri` is publicly reachable and returns a JSON object with a `keys` array.

## Requests unexpectedly return 429

`DEFAULT_RATE_LIMIT` is enforced independently in each Gunicorn worker using in-memory state. The default deployment has two workers in each of two replicas, so it does not provide one shared cluster-wide counter. Load balancing can therefore allow more requests than the configured value across the complete deployment. If a globally consistent limit is required, enforce it at the ingress, API gateway, or WAF.

The limiter uses the first (left-most) address in the edge-normalized `X-Forwarded-For` chain, so callers remain distinct whether traffic crosses only a gateway or also crosses a WAF and load balancer. If that value is absent or malformed, it falls back to the connected peer. See [External caller identity and rate limiting](getting-started.md#external-caller-identity-and-rate-limiting).

The JSON access log's `remote_ip` field uses that same resolved address. Its `forwarded_for` field preserves the raw `X-Forwarded-For` chain for troubleshooting and must not be treated as an authenticated client identity. This is independent of the proxy product, but the proxy must sanitize or append `X-Forwarded-For`; a proxy that sends only `Forwarded` or `X-Real-IP` needs to be configured to emit `X-Forwarded-For` as well.

If `remote_ip` is a proxy address, inspect `forwarded_for` and configure the public edge to emit a normalized `X-Forwarded-For` chain. If different users unexpectedly share or evade limits, confirm that the edge removes caller-supplied values before creating that chain.

## The public route returns 404, 502, or a TLS error

The route manifests intentionally expose only `/.well-known/openid-configuration` and `/openid/v1/jwks` with exact path matching. A request to `/` returning 404 is expected.

For Gateway API, inspect the route's `Accepted`, `ResolvedRefs`, and parent conditions:

```bash
kubectl describe httproute kube-oidc-issuer-reflector \
  -n kube-oidc-issuer-reflector
kubectl get gateway -A
```

Confirm that `GATEWAY_NAME`, `GATEWAY_NAMESPACE`, and `GATEWAY_LISTENER_NAME` identify an existing HTTPS listener and that the listener permits routes from the reflector namespace. TLS certificates are configured on that listener, not by the included `HTTPRoute`.

For Ingress, inspect its selected class, events, address, and TLS Secret:

```bash
kubectl describe ingress kube-oidc-issuer-reflector \
  -n kube-oidc-issuer-reflector
kubectl get ingressclass
kubectl get secret kube-oidc-issuer-reflector-tls \
  -n kube-oidc-issuer-reflector
```

If the route is accepted but returns 502, verify the Service endpoints and readiness state:

```bash
kubectl get pods,service,endpoints -n kube-oidc-issuer-reflector
kubectl logs -n kube-oidc-issuer-reflector \
  -l app=kube-oidc-issuer-reflector --all-containers --prefix
```
