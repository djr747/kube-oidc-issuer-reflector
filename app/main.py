import json
import logging
import math
import os
import threading
import time
import typing as t

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect
from kubernetes import client, config

from app.client_ip import resolve_client_ip

default_rate_limit = os.environ.get("DEFAULT_RATE_LIMIT", "10 per second")


def _non_negative_float_env(name: str, default: str) -> float:
    raw_value = os.environ.get(name, default)
    try:
        value = float(raw_value)
    except ValueError as e:
        raise ValueError(f"{name} must be a number") from e
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return value


def _positive_int_env(name: str, default: str) -> int:
    raw_value = os.environ.get(name, default)
    try:
        value = int(raw_value)
    except ValueError as e:
        raise ValueError(f"{name} must be an integer") from e
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


# Each worker caches only the two fixed OIDC endpoint documents. The per-document
# size limit keeps memory bounded even if an upstream response is unexpectedly large.
OIDC_DOCUMENT_CACHE_TTL_SECONDS = _non_negative_float_env("OIDC_DOCUMENT_CACHE_TTL_SECONDS", "30")
OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS = _non_negative_float_env(
    "OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS", "300"
)
OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS = _non_negative_float_env(
    "OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS", "5"
)
OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES = _positive_int_env(
    "OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES", str(1024 * 1024)
)

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True
csrf = CSRFProtect()
csrf.init_app(app)


class _CacheEntry(t.NamedTuple):
    document: dict[str, t.Any]
    fetched_at: float


_oidc_document_cache: dict[str, _CacheEntry] = {}
_oidc_document_cache_retry_after: dict[str, float] = {}
_oidc_document_cache_guard = threading.Lock()
_oidc_document_refresh_locks = {
    "openid_configuration": threading.Lock(),
    "jwks": threading.Lock(),
}


def fetch_with_cache(
    cache_key: str,
    fetch_document: t.Callable[[], dict[str, t.Any]],
) -> dict[str, t.Any]:
    """Fetch a validated endpoint document, using fresh or eligible stale data.

    A separate lock for each fixed endpoint prevents concurrent requests from
    multiplying API calls while allowing discovery and JWKS refreshes in parallel.
    """
    if cache_key not in _oidc_document_refresh_locks:
        raise ValueError("Unknown OIDC document cache key")

    def is_eligible_stale(entry: _CacheEntry | None, now: float) -> bool:
        return (
            entry is not None
            and now - entry.fetched_at
            <= OIDC_DOCUMENT_CACHE_TTL_SECONDS + OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS
        )

    now = time.monotonic()
    with _oidc_document_cache_guard:
        entry = _oidc_document_cache.get(cache_key)
        retry_after = _oidc_document_cache_retry_after.get(cache_key, 0.0)
    if entry is not None and now - entry.fetched_at <= OIDC_DOCUMENT_CACHE_TTL_SECONDS:
        return entry.document
    if entry is not None and is_eligible_stale(entry, now) and now < retry_after:
        return entry.document

    with _oidc_document_refresh_locks[cache_key]:
        # Another request may have refreshed while this request waited.
        now = time.monotonic()
        with _oidc_document_cache_guard:
            entry = _oidc_document_cache.get(cache_key)
            retry_after = _oidc_document_cache_retry_after.get(cache_key, 0.0)
        if entry is not None and now - entry.fetched_at <= OIDC_DOCUMENT_CACHE_TTL_SECONDS:
            return entry.document
        if entry is not None and is_eligible_stale(entry, now) and now < retry_after:
            return entry.document

        try:
            document = fetch_document()
        except Exception:
            now = time.monotonic()
            if entry is not None and is_eligible_stale(entry, now):
                with _oidc_document_cache_guard:
                    _oidc_document_cache_retry_after[cache_key] = (
                        now + OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS
                    )
                app.logger.warning(
                    "Serving stale Kubernetes OIDC response after upstream fetch failure: endpoint=%s",
                    cache_key,
                )
                return entry.document
            raise

        # Count the compact JSON representation before retaining it. Oversized
        # documents are still returned to the caller but are not cached.
        document_bytes = len(json.dumps(document, separators=(",", ":")).encode("utf-8"))
        with _oidc_document_cache_guard:
            _oidc_document_cache_retry_after.pop(cache_key, None)
            if document_bytes <= OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES:
                _oidc_document_cache[cache_key] = _CacheEntry(document, time.monotonic())
            else:
                _oidc_document_cache.pop(cache_key, None)
                app.logger.warning(
                    "Not caching oversized Kubernetes OIDC response: endpoint=%s bytes=%d limit=%d",
                    cache_key,
                    document_bytes,
                    OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES,
                )
        return document


def get_client_ip() -> str:
    """Return the external caller address normalized by the public edge."""
    return resolve_client_ip(request.headers.get("X-Forwarded-For"), request.remote_addr)


limiter = Limiter(
    get_client_ip,
    app=app,
    default_limits=[default_rate_limit],
    storage_uri="memory://",
)


class EndpointFilter(logging.Filter):
    def __init__(
        self,
        path: str,
        *args: t.Any,
        **kwargs: t.Any,
    ) -> None:
        """Initialize the EndpointFilter instance.

        Args:
            path: The URL path that should be excluded from the log output.
            *args: Additional positional arguments passed to the superclass.
            **kwargs: Additional keyword arguments passed to the superclass.
        """
        super().__init__(*args, **kwargs)
        self._path = path

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True if the record should be processed, False otherwise.

        Args:
            record: The log record to evaluate.

        Returns:
            True if the record does not contain the filtered path.
        """
        return record.getMessage().find(self._path) == -1


# Setup logging
gunicorn_error_logger = logging.getLogger("gunicorn.error")
app.logger.handlers = gunicorn_error_logger.handlers
app.logger.setLevel(gunicorn_error_logger.level)
gunicorn_access_logger = logging.getLogger("gunicorn.access")
gunicorn_access_logger.addFilter(EndpointFilter(path="/livez"))
gunicorn_access_logger.addFilter(EndpointFilter(path="/readyz"))


def get_k8s_client() -> client:
    """Return a Kubernetes client based on the runtime environment.

    Detects in-cluster vs local kubeconfig automatically.

    Returns:
        The Kubernetes client object.
    """
    if "KUBERNETES_SERVICE_HOST" in os.environ:
        config.load_incluster_config()
    else:
        config.load_kube_config()

    return client


def get_kubernetes_request_timeout() -> float:
    """Return the configured client-side timeout for Kubernetes API requests."""
    raw_timeout = os.environ.get("KUBERNETES_REQUEST_TIMEOUT_SECONDS", "5")
    try:
        timeout = float(raw_timeout)
    except ValueError as e:
        raise ValueError("KUBERNETES_REQUEST_TIMEOUT_SECONDS must be a number") from e

    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("KUBERNETES_REQUEST_TIMEOUT_SECONDS must be finite and greater than zero")
    return timeout


def validate_openid_configuration(document: t.Any) -> dict[str, t.Any]:
    """Validate the minimum fields required in an issuer discovery document."""
    if not isinstance(document, dict):
        raise ValueError("OIDC discovery document must be a JSON object")
    for field in ("issuer", "jwks_uri"):
        if not isinstance(document.get(field), str) or not document[field]:
            raise ValueError(f"OIDC discovery document has an invalid {field!r} field")
    return t.cast(dict[str, t.Any], document)


def validate_jwks(document: t.Any) -> dict[str, t.Any]:
    """Validate the minimum shape required in a JSON Web Key Set."""
    if not isinstance(document, dict):
        raise ValueError("JWKS document must be a JSON object")
    keys = document.get("keys")
    if not isinstance(keys, list) or not all(isinstance(key, dict) for key in keys):
        raise ValueError("JWKS document has an invalid 'keys' field")
    return t.cast(dict[str, t.Any], document)


def fetch_openid_configuration() -> dict[str, t.Any]:
    """Fetch and validate the discovery document from the Kubernetes API."""
    k8s = get_k8s_client()
    with k8s.ApiClient() as api_client:
        api = k8s.WellKnownApi(api_client)
        api_response: client.ApiResponse = api.get_service_account_issuer_open_id_configuration(
            _preload_content=False,
            _request_timeout=get_kubernetes_request_timeout(),
        )
        return validate_openid_configuration(json.loads(api_response.data))


def fetch_jwks() -> dict[str, t.Any]:
    """Fetch and validate the JSON Web Key Set from the Kubernetes API."""
    k8s = get_k8s_client()
    with k8s.ApiClient() as api_client:
        api = k8s.OpenidApi(api_client)
        api_response: client.ApiResponse = api.get_service_account_issuer_open_id_keyset(
            _preload_content=False,
            _request_timeout=get_kubernetes_request_timeout(),
        )
        return validate_jwks(json.loads(api_response.data))


# Route for OIDC discovery document which contains the metadata about the issuer's configurations
@app.route("/.well-known/openid-configuration", methods=["GET"])
def get_openid_configuration() -> tuple[t.Any, int]:
    """Handle GET request to the OIDC discovery endpoint.

    Reflects the OIDC discovery document from the Kubernetes API server.

    Returns:
        A tuple of the JSON response body and HTTP status code.
    """
    if app.logger.isEnabledFor(logging.DEBUG):
        app.logger.debug("Incoming request: path=/.well-known/openid-configuration")

    allowed_user_agent = os.environ.get("ALLOWED_USER_AGENT")
    if allowed_user_agent and request.headers.get("User-Agent") != allowed_user_agent:
        return "Forbidden", 403

    try:
        openid_configuration = fetch_with_cache("openid_configuration", fetch_openid_configuration)
    except Exception:
        app.logger.exception("Unable to fetch Kubernetes OIDC discovery document")
        return "Upstream Kubernetes API error", 502

    return jsonify(openid_configuration), 200


# Route for JSON Web Key Sets (JWKS) document which contains the public signing key(s) for service accounts
@app.route("/openid/v1/jwks", methods=["GET"])
def get_jwks() -> tuple[t.Any, int]:
    """Return the JWKS document containing public signing keys for service accounts.

    Returns:
        A tuple of the JSON response body and HTTP status code.
    """
    if app.logger.isEnabledFor(logging.DEBUG):
        app.logger.debug("Incoming request: path=/openid/v1/jwks")

    allowed_user_agent = os.environ.get("ALLOWED_USER_AGENT")
    if allowed_user_agent and request.headers.get("User-Agent") != allowed_user_agent:
        return "Forbidden", 403

    try:
        jwks = fetch_with_cache("jwks", fetch_jwks)
    except Exception:
        app.logger.exception("Unable to fetch Kubernetes JWKS document")
        return "Upstream Kubernetes API error", 502

    return jsonify(jwks), 200


@app.route("/livez", methods=["GET"])
@limiter.exempt
def health_liveness() -> tuple[str, int]:
    """Kubernetes liveness probe handler.

    Returns 200 to indicate the process is alive. This probe does not
    make Kubernetes API calls; it only confirms the Gunicorn worker
    is responsive.

    Returns:
        A tuple of the health status string and HTTP status code.
    """
    return "I am alive!", 200


@app.route("/readyz", methods=["GET"])
@limiter.exempt
def health_readiness() -> tuple[str, int]:
    """Kubernetes readiness probe handler.

    Returns 200 when both documents can be fetched and validated or served
    from eligible cache entries. Returns 503 when either document is
    unavailable so Kubernetes stops routing traffic to this pod.

    Returns:
        A tuple of the readiness status string and HTTP status code.
    """
    try:
        fetch_with_cache("openid_configuration", fetch_openid_configuration)
        fetch_with_cache("jwks", fetch_jwks)
    except Exception:
        app.logger.exception("Readiness check failed")
        return "I am not ready!", 503

    return "I am ready!", 200
