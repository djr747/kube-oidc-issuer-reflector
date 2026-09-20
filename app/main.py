import json
import logging
import os
import typing as t

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect
from kubernetes import client, config

from app.client_ip import resolve_client_ip

default_rate_limit = os.environ.get("DEFAULT_RATE_LIMIT", "10 per second")

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True
csrf = CSRFProtect()
csrf.init_app(app)


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

    if timeout <= 0:
        raise ValueError("KUBERNETES_REQUEST_TIMEOUT_SECONDS must be greater than zero")
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
        app.logger.debug(
            "Incoming request: method=%s path=%s remote_addr=%s",
            request.method,
            request.path,
            get_client_ip(),
        )

    allowed_user_agent = os.environ.get("ALLOWED_USER_AGENT")
    if allowed_user_agent and request.headers.get("User-Agent") != allowed_user_agent:
        return "Forbidden", 403

    try:
        openid_configuration = fetch_openid_configuration()
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
        app.logger.debug(
            "Incoming request: method=%s path=%s remote_addr=%s",
            request.method,
            request.path,
            get_client_ip(),
        )

    allowed_user_agent = os.environ.get("ALLOWED_USER_AGENT")
    if allowed_user_agent and request.headers.get("User-Agent") != allowed_user_agent:
        return "Forbidden", 403

    try:
        jwks = fetch_jwks()
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

    Returns 200 only when the Kubernetes OIDC discovery and JWKS
    endpoints are accessible and return parseable JSON. Returns 503
    on any failure so Kubernetes stops routing traffic to this pod.

    Returns:
        A tuple of the readiness status string and HTTP status code.
    """
    try:
        fetch_openid_configuration()
        fetch_jwks()
    except Exception:
        app.logger.exception("Readiness check failed")
        return "I am not ready!", 503

    return "I am ready!", 200
