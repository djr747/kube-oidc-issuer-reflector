import json
import logging
import os
import traceback
import typing as t

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from kubernetes import client, config

default_rate_limit = os.environ.get("DEFAULT_RATE_LIMIT", "10 per second")

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
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
if __name__ != "__main__":
    gunicorn_error_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_error_logger.handlers
    app.logger.setLevel(gunicorn_error_logger.level)
    gunicorn_access_logger = logging.getLogger("gunicorn.access")
    gunicorn_access_logger.addFilter(EndpointFilter(path="/livez"))
    gunicorn_access_logger.addFilter(EndpointFilter(path="/readyz"))


def get_exception_description(e: Exception) -> str:
    """Return a single-line string describing the exception.

    Args:
        e: The exception to describe.

    Returns:
        A single-line string with the exception type and message.
    """
    exc_desc_lines = traceback.format_exception_only(type(e), e)
    exc_desc = "".join(exc_desc_lines).rstrip()
    return exc_desc


def get_k8s_client() -> client:
    """Return a Kubernetes client based on the runtime environment.

    Detects in-cluster vs local kubeconfig automatically.

    Returns:
        The Kubernetes client object.
    """
    if "KUBERNETES_SERVICE_HOST" in os.environ:
        config.load_incluster_config()
    else:
        try:
            config.load_kube_config()
        except config.ConfigException as e:
            app.logger.error(get_exception_description(e))

    return client


# Route for OIDC discovery document which contains the metadata about the issuer's configurations
@app.route("/.well-known/openid-configuration", methods=["GET"])
def get_openid_configuration() -> tuple[t.Any, int]:
    """Handle GET request to the OIDC discovery endpoint.

    Reflects the OIDC discovery document from the Kubernetes API server.

    Returns:
        A tuple of the JSON response body and HTTP status code.
    """
    if app.logger.level == logging.DEBUG:
        app.logger.debug(
            f"Incoming request: method={request.method} path={request.path} headers={dict(request.headers)}"
        )

    allowed_user_agent = os.environ.get("ALLOWED_USER_AGENT")
    if allowed_user_agent and request.headers.get("User-Agent") != allowed_user_agent:
        return "Forbidden", 403

    try:
        k8s_client: client.WellKnownApi = get_k8s_client().WellKnownApi()

        api_response: client.ApiResponse = (
            k8s_client.get_service_account_issuer_open_id_configuration(_preload_content=False)
        )

        openid_configuration: dict = json.loads(api_response.data)
    except Exception as e:
        app.logger.error(f"kubernetes.client.WellKnownApi.Exception: {e}")
        return "Internal error check logs", 500

    return jsonify(openid_configuration), 200


# Route for JSON Web Key Sets (JWKS) document which contains the public signing key(s) for service accounts
@app.route("/openid/v1/jwks", methods=["GET"])
def get_jwks() -> tuple[t.Any, int]:
    """Return the JWKS document containing public signing keys for service accounts.

    Returns:
        A tuple of the JSON response body and HTTP status code.
    """
    if app.logger.level == logging.DEBUG:
        app.logger.debug(
            f"Incoming request: method={request.method} path={request.path} headers={dict(request.headers)}"
        )

    allowed_user_agent = os.environ.get("ALLOWED_USER_AGENT")
    if allowed_user_agent and request.headers.get("User-Agent") != allowed_user_agent:
        return "Forbidden", 403

    try:
        k8s_client: client.OpenidApi = get_k8s_client().OpenidApi()

        api_response: client.ApiResponse = k8s_client.get_service_account_issuer_open_id_keyset(
            _preload_content=False
        )

        jwks: str = json.loads(api_response.data)
    except Exception as e:
        app.logger.error(f"kubernetes.client.OpenidApi.Exception: {e}")
        return "Internal error check logs", 500

    return jsonify(jwks), 200


@app.route("/livez")
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


@app.route("/readyz")
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
        k8s = get_k8s_client()
        discovery_response: client.ApiResponse = (
            k8s.WellKnownApi().get_service_account_issuer_open_id_configuration(
                _preload_content=False
            )
        )
        jwks_response: client.ApiResponse = (
            k8s.OpenidApi().get_service_account_issuer_open_id_keyset(_preload_content=False)
        )
        json.loads(discovery_response.data)
        json.loads(jwks_response.data)
    except Exception as e:
        app.logger.error(f"Readiness check failed: {e}")
        return "I am not ready!", 503

    return "I am ready!", 200


if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=8080)
