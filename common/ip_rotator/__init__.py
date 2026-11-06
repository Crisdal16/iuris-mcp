"""
ip_rotator
==========

Sistema de rotación de IPs para scraping (pool de hasta 99 proxies
HTTP/HTTPS propios, con auto-recovery y API de integración).

Ejemplo rápido:
    from ip_rotator import ProxyRotator

    rot = ProxyRotator(["1.2.3.4:8080", "user:pass@5.6.7.8:3128"])
    r = rot.request("GET", "https://httpbin.org/ip")
    print(r.ok, r.status_code, r.proxy_used)
"""

from .rotator import (
    MAX_POOL_SIZE,
    Attempt,
    DuplicateProxyError,
    PoolFullError,
    Proxy,
    ProxyRotator,
    ProxyRotatorError,
    ProxyStatus,
    RotationResult,
    RotationStrategy,
    parse_proxy,
)
from .storage import ProxyStore

__version__ = "1.0.0"

__all__ = [
    "MAX_POOL_SIZE",
    "Attempt",
    "DuplicateProxyError",
    "PoolFullError",
    "Proxy",
    "ProxyRotator",
    "ProxyRotatorError",
    "ProxyStatus",
    "RotationResult",
    "RotationStrategy",
    "ProxyStore",
    "parse_proxy",
    "__version__",
]
