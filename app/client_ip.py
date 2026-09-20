"""Resolve the external caller address supplied by the edge proxy."""

import ipaddress


def resolve_client_ip(forwarded_for: str | None, peer_address: str | None) -> str:
    """Return the left-most valid forwarded address, or the socket peer.

    The public ingress, gateway, or WAF is responsible for removing any
    caller-supplied forwarding header before it appends its normalized chain.
    """
    if forwarded_for and forwarded_for != "-":
        candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass

    if peer_address:
        try:
            return str(ipaddress.ip_address(peer_address))
        except ValueError:
            return peer_address

    return "-"
