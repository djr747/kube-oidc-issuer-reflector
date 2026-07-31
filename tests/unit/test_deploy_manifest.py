"""Unit tests for the Kubernetes deployment manifest (deploy/deploy.yaml)."""

from pathlib import Path

import pytest
import yaml

_DEPLOY_FILE = Path(__file__).parent.parent.parent / "deploy" / "deploy.yaml"


def _load_documents():
    """Load all YAML documents from deploy.yaml."""
    with open(_DEPLOY_FILE) as f:
        return list(yaml.safe_load_all(f))


def _find_kind(docs, kind):
    """Return the first document of the given kind."""
    for doc in docs:
        if doc and doc.get("kind") == kind:
            return doc
    return None


class TestManifestStructure:
    """Validate structural correctness of deploy.yaml."""

    @pytest.fixture
    def docs(self):
        return _load_documents()

    def test_all_documents_valid(self, docs):
        """Every YAML document parses to a non-empty dict or None (separator)."""
        for doc in docs:
            assert doc is None or isinstance(doc, dict)

    def test_namespace_exists(self, docs):
        """A Namespace resource is defined."""
        ns = _find_kind(docs, "Namespace")
        assert ns is not None
        assert ns["metadata"]["name"] == "kube-oidc-issuer-reflector"

    def test_service_account_exists(self, docs):
        """A ServiceAccount is defined in the correct namespace."""
        sa = _find_kind(docs, "ServiceAccount")
        assert sa is not None
        assert sa["metadata"]["name"] == "kube-oidc-issuer-reflector"
        assert sa["metadata"]["namespace"] == "kube-oidc-issuer-reflector"

    def test_role_exists(self, docs):
        """A Role is defined with get on the expected authentication resources."""
        role = _find_kind(docs, "Role")
        assert role is not None
        assert role["metadata"]["namespace"] == "kube-oidc-issuer-reflector"
        rules = role["rules"]
        assert any(
            "get" in r.get("verbs", []) and "authentication.k8s.io" in r.get("apiGroups", [])
            for r in rules
        )

    def test_role_binding_exists(self, docs):
        """A RoleBinding binds the ServiceAccount to the Role."""
        rb = _find_kind(docs, "RoleBinding")
        assert rb is not None
        assert rb["roleRef"]["kind"] == "Role"
        assert rb["roleRef"]["name"] == "kube-oidc-issuer-reflector"
        subjects = rb["subjects"]
        assert any(
            s["kind"] == "ServiceAccount"
            and s["name"] == "kube-oidc-issuer-reflector"
            and s["namespace"] == "kube-oidc-issuer-reflector"
            for s in subjects
        )

    def test_deployment_exists(self, docs):
        """A Deployment is defined with correct selectors and probes."""
        dep = _find_kind(docs, "Deployment")
        assert dep is not None
        assert dep["metadata"]["namespace"] == "kube-oidc-issuer-reflector"

        spec = dep["spec"]
        assert spec["replicas"] == 2
        assert spec["selector"]["matchLabels"]["app"] == "kube-oidc-issuer-reflector"
        assert spec["template"]["metadata"]["labels"]["app"] == "kube-oidc-issuer-reflector"

    def test_deployment_uses_service_account(self, docs):
        """The Deployment pod template references the correct ServiceAccount."""
        dep = _find_kind(docs, "Deployment")
        template_spec = dep["spec"]["template"]["spec"]
        assert template_spec["serviceAccountName"] == "kube-oidc-issuer-reflector"

    def test_deployment_probes(self, docs):
        """Liveness and readiness probes are configured on the correct paths and ports."""
        dep = _find_kind(docs, "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]

        liveness = container["livenessProbe"]
        assert liveness["httpGet"]["path"] == "/livez"
        assert liveness["httpGet"]["port"] == 8080

        readiness = container["readinessProbe"]
        assert readiness["httpGet"]["path"] == "/readyz"
        assert readiness["httpGet"]["port"] == 8080

    def test_deployment_resources(self, docs):
        """Container resources have requests and limits set."""
        dep = _find_kind(docs, "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]

        assert "requests" in resources
        assert "limits" in resources
        assert "memory" in resources["requests"]
        assert "cpu" in resources["requests"]
        assert "memory" in resources["limits"]
        assert "cpu" in resources["limits"]

    def test_deployment_uses_canonical_image_and_hardening(self, docs):
        """The deployment runs the canonical non-root Chainguard image configuration."""
        dep = _find_kind(docs, "Deployment")
        pod_spec = dep["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]

        assert container["image"] == "ghcr.io/djr747/kube-oidc-issuer-reflector:latest"
        assert container["imagePullPolicy"] == "IfNotPresent"
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert pod_spec["securityContext"]["runAsUser"] == 65532
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["readOnlyRootFilesystem"] is True

    def test_service_exists(self, docs):
        """A Service routes traffic to the Deployment on the correct port."""
        svc = _find_kind(docs, "Service")
        assert svc is not None
        assert svc["spec"]["selector"]["app"] == "kube-oidc-issuer-reflector"

        ports = svc["spec"]["ports"]
        assert len(ports) == 1
        assert ports[0]["port"] == 80
        assert ports[0]["targetPort"] == 8080

    def test_ingress_exists(self, docs):
        """An Ingress is defined for the OIDC paths."""
        ing = _find_kind(docs, "Ingress")
        assert ing is not None
        assert ing["spec"]["ingressClassName"] == "nginx"

        rules = ing["spec"]["rules"]
        assert len(rules) == 1
        paths = rules[0]["http"]["paths"]
        path_values = [p["path"] for p in paths]
        assert "/.well-known/openid-configuration" in path_values
        assert "/openid/v1/jwks" in path_values

    def test_container_port(self, docs):
        """The container exposes port 8080."""
        dep = _find_kind(docs, "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        ports = container["ports"]
        assert any(p["containerPort"] == 8080 for p in ports)
