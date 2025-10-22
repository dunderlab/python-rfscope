"""
API Request Signer
==================

HTTP client with Ed25519 SSH key–based request signing.

This module enables sending authenticated HTTP requests using locally stored
Ed25519 private SSH keys. It includes utilities for cryptographic operations,
canonical string construction, and Ed25519 signature generation, ensuring
secure and verifiable communication between clients and servers.

Example
-------
>>> from api_requests import signed_request
>>> response = signed_request(
...     url="https://example.com/api/data/",
...     method="POST",
...     json_body={"value": 123},
...     priv_path="~/.ssh/id_ed25519"
... )
>>> print(response.status_code, response.text)
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlsplit
from wsgiref.handlers import format_date_time

import requests
from cryptography.hazmat.primitives.serialization import (
    load_ssh_private_key,
    Encoding,
    PublicFormat,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def rfc1123_now() -> str:
    """
    Return the current UTC time formatted according to RFC 1123.

    Returns
    -------
    str
        The current UTC date and time in RFC 1123 format.
    """
    return format_date_time(datetime.now(timezone.utc).timestamp())


def sha256_b64(data: bytes) -> str:
    """
    Compute the SHA-256 hash of the given data and return it in Base64 encoding.

    Parameters
    ----------
    data : bytes
        The input data.

    Returns
    -------
    str
        The Base64-encoded SHA-256 hash (without '=' padding).
    """
    return base64.b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")


def compute_fp_from_openssh_pub(pub_openssh: bytes) -> str:
    """
    Compute the SHA-256 fingerprint from an OpenSSH public key.

    Parameters
    ----------
    pub_openssh : bytes
        The OpenSSH public key, e.g. b"ssh-ed25519 AAAA... comment".

    Returns
    -------
    str
        The fingerprint in the format "SHA256:xxxx".
    """
    key_b64 = pub_openssh.split()[1]
    raw = base64.b64decode(key_b64)
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip(
        "="
    )


def load_ed25519_private(path: str, password: bytes | None = None) -> Ed25519PrivateKey:
    """
    Load an Ed25519 private key from an SSH private key file.

    Parameters
    ----------
    path : str
        Path to the private key file.
    password : bytes, optional
        Password for the key if encrypted.

    Returns
    -------
    Ed25519PrivateKey
        The loaded private key object.
    """
    return load_ssh_private_key(pathlib.Path(path).read_bytes(), password=password)


def openssh_public_from_private(priv: Ed25519PrivateKey) -> bytes:
    """
    Extract the OpenSSH-formatted public key from a private Ed25519 key.

    Parameters
    ----------
    priv : Ed25519PrivateKey
        The Ed25519 private key.

    Returns
    -------
    bytes
        The public key encoded in OpenSSH format.
    """
    pub = priv.public_key()
    return pub.public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)


def canonical_string(method: str, path: str, date_hdr: str, digest_hdr: str) -> bytes:
    """
    Build the canonical string that must be signed.

    Parameters
    ----------
    method : str
        HTTP method (GET, POST, etc.).
    path : str
        The path and query (without host or scheme).
    date_hdr : str
        The 'Date' header in RFC 1123 format.
    digest_hdr : str
        The SHA-256 hash of the request body in Base64.

    Returns
    -------
    bytes
        The canonical string encoded as bytes.
    """
    return (
        f"{method.upper()}\n{path}\n{date_hdr}\nDigest: SHA-256={digest_hdr}\n".encode()
    )


def sign_ed25519(priv: Ed25519PrivateKey, data: bytes) -> str:
    """
    Sign data using an Ed25519 private key and return the signature in Base64.

    Parameters
    ----------
    priv : Ed25519PrivateKey
        The private key used for signing.
    data : bytes
        The data to be signed.

    Returns
    -------
    str
        The Base64-encoded signature.
    """
    sig = priv.sign(data)
    return base64.b64encode(sig).decode()


def signed_request(
    url: str,
    method: str = "POST",
    json_body: dict | None = None,
    priv_path: str = "~/.ssh/id_ed25519",
    priv_password: bytes | None = None,
    key_id: str | None = None,
    extra_headers: dict | None = None,
    verify_tls: bool | str = True,
) -> requests.Response:
    """
    Send an HTTP request signed with an Ed25519 SSH key.

    Parameters
    ----------
    url : str
        Full endpoint URL (including scheme and host).
    method : str, default="POST"
        HTTP method (POST, GET, PUT, etc.).
    json_body : dict, optional
        The JSON payload to send in the request body.
    priv_path : str, default="~/.ssh/id_ed25519"
        Path to the private SSH key file.
    priv_password : bytes, optional
        Password for the private key, if encrypted.
    key_id : str, optional
        Manually provided key identifier; if not given, the fingerprint is computed.
    extra_headers : dict, optional
        Additional HTTP headers to include.
    verify_tls : bool or str, default=True
        TLS verification setting (True, False, or path to CA bundle).

    Returns
    -------
    requests.Response
        The HTTP response object.
    """
    priv = load_ed25519_private(
        pathlib.Path(priv_path).expanduser(), password=priv_password
    )
    pub_ssh = openssh_public_from_private(priv)
    fp = key_id or compute_fp_from_openssh_pub(pub_ssh)

    body_bytes = b""
    if json_body is not None:
        body_bytes = json.dumps(
            json_body, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    digest_b64 = sha256_b64(body_bytes)
    date_hdr = rfc1123_now()

    # PSS: Ensured only path + query are signed (excluding scheme and host)
    parts = urlsplit(url)
    path_and_query = parts.path + (("?" + parts.query) if parts.query else "")

    to_sign = canonical_string(method, path_and_query, date_hdr, digest_b64)
    signature_b64 = sign_ed25519(priv, to_sign)

    headers = {
        "Date": date_hdr,
        "Digest": f"SHA-256={digest_b64}",
        "X-SSH-Key-Id": fp,
        "X-SSH-Signature-Alg": "ssh-ed25519",
        "X-SSH-Signature": signature_b64,
        "Content-Type": "application/json",
    }

    if extra_headers:
        headers.update(extra_headers)

    response = requests.request(
        method, url, data=body_bytes, headers=headers, verify=verify_tls
    )
    return response


def _test_signed_request_example() -> None:
    """
    Simple unit test example for `signed_request`.

    This test does not perform real network requests. It only checks
    that headers and signature fields are properly constructed.

    Notes
    -----
    Requires a valid private key file at `~/.ssh/id_ed25519`.
    """
    import types

    def mock_request(method, url, data, headers, verify):
        return types.SimpleNamespace(status_code=200, text="OK", headers=headers)

    requests.request = mock_request  # type: ignore

    response = signed_request("https://localhost/test", json_body={"a": 1})
    assert response.status_code == 200
    assert "X-SSH-Signature" in response.headers


if __name__ == "__main__":
    _test_signed_request_example()
