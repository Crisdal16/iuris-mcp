"""
ip_rotator.rotator
==================

Núcleo del sistema de rotación de IPs para scraping.

Diseño:
    - Pool de hasta MAX_POOL_SIZE (99) proxies HTTP/HTTPS propios.
    - Rotación automática a la siguiente IP cuando una petición falla
      (error de transporte, timeout, o estados bloqueantes 403/429/503).
    - Auto-recovery: un proxy que falla entra en COOLDOWN durante
      `cooldown_seconds` y vuelve a estar disponible solo; si acumula
      `max_consecutive_failures` fallos seguidos pasa a DEAD y se
      re-intenta tras `dead_revive_seconds`.
    - Thread-safe (todas las mutaciones de estado van bajo lock; la
      petición HTTP en sí se hace fuera del lock).
    - Cliente-agnóstico: adaptadores incluidos para `requests` y `httpx`,
      y métodos `next_proxy()` / `report_*()` para integraciones externas
      (p. ej. un proyecto que usa Selenium, cloudscraper o su propia
      sesión ya configurada).

Uso mínimo:
    from ip_rotator import ProxyRotator

    rot = ProxyRotator(["1.2.3.4:8080", "user:pass@5.6.7.8:3128"])
    r = rot.request("GET", "https://httpbin.org/ip")
    if r.ok:
        print(r.status_code, r.body, "-> salió por", r.proxy_used)

Uso integrado con una sesión propia (p. ej. cloudscraper):
    rot.request("GET", url, session=mi_session)   # respeta cabeceras/cookies
"""

from __future__ import annotations

import itertools
import random
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "MAX_POOL_SIZE",
    "Attempt",
    "Proxy",
    "ProxyRotator",
    "ProxyRotatorError",
    "ProxyStatus",
    "PoolFullError",
    "DuplicateProxyError",
    "RotationResult",
    "RotationStrategy",
    "parse_proxy",
]

#: Tamaño máximo del pool solicitado por el usuario.
MAX_POOL_SIZE = 99

#: Estados HTTP que se consideran "la IP está bloqueada/limitada" y provocan
#: rotación automática a la siguiente IP.
RETRYABLE_STATUS_DEFAULT: Tuple[int, ...] = (403, 429, 503)


class ProxyRotatorError(Exception):
    """Error base del módulo."""


class PoolFullError(ProxyRotatorError):
    """El pool ya alcanzó max_pool_size."""


class DuplicateProxyError(ProxyRotatorError):
    """El proxy ya existe en el pool."""


class ProxyStatus(str, Enum):
    UNTESTED = "untested"    # cargado pero aún sin usar
    ACTIVE = "active"        # funcionando
    COOLDOWN = "cooldown"    # falló; esperando reintento automático
    DEAD = "dead"            # demasiados fallos seguidos; re-intento tardío


class RotationStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"    # turnos: la menos usada recientemente primero
    RANDOM = "random"              # aleatoria entre las disponibles
    LEAST_USED = "least_used"      # la que menos peticiones totales lleva


# --------------------------------------------------------------------------- #
# Modelo de datos
# --------------------------------------------------------------------------- #

@dataclass
class Proxy:
    """Un proxy del pool y sus estadísticas de uso."""

    raw: str
    scheme: str = "http"
    host: str = ""
    port: int = 0
    username: Optional[str] = None
    password: Optional[str] = None

    status: ProxyStatus = ProxyStatus.UNTESTED
    consecutive_failures: int = 0
    total_requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0

    last_used: float = 0.0
    last_failure_at: float = 0.0
    cooldown_until: float = 0.0
    last_error: str = ""
    added_at: float = field(default_factory=time.time)

    @property
    def id(self) -> str:
        """Identificador único dentro del pool: host:puerto."""
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        """URL completa del proxy para clientes HTTP."""
        auth = ""
        if self.username:
            auth = f"{self.username}:{self.password or ''}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def avg_latency(self) -> float:
        """Latencia media de los éxitos, en segundos (0.0 si no hay datos)."""
        return (self.total_latency / self.successes) if self.successes else 0.0

    @property
    def success_rate(self) -> float:
        if self.total_requests <= 0:
            return 0.0
        return self.successes / self.total_requests

    def masked(self) -> str:
        """Representación corta y segura para logs/resultados."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "scheme": self.scheme,
            "has_auth": bool(self.username),
            "status": self.status.value,
            "cooldown_remaining_s": max(0.0, round(self.cooldown_until - now, 1))
            if self.status == ProxyStatus.COOLDOWN
            else 0.0,
            "total_requests": self.total_requests,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency * 1000, 1),
            "consecutive_failures": self.consecutive_failures,
            "last_used_ago_s": round(now - self.last_used, 1) if self.last_used else None,
            "last_error": self.last_error,
            "added_at": self.added_at,
        }


def parse_proxy(raw: str, default_scheme: str = "http") -> Proxy:
    """
    Convierte una cadena en un :class:`Proxy`.

    Formatos aceptados (uno por línea en proxies.txt):
        ip:puerto
        ip:puerto:usuario:clave
        http://ip:puerto
        http://usuario:clave@ip:puerto
        https://...            (mismo formato anterior con scheme https)

    Las líneas vacías o que empiezan por ``#`` se ignoran si llegan aquí se
    rechazan con ValueError (el loader de fichero filtra comentarios antes).
    """
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        raise ValueError("línea vacía o comentario")

    scheme = default_scheme.lower()
    rest = s
    if "://" in s:
        scheme, rest = s.split("://", 1)
        scheme = scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError(f"protocolo no soportado: {scheme!r} (solo http/https)")

    username: Optional[str] = None
    password: Optional[str] = None
    if "@" in rest:
        auth, rest = rest.rsplit("@", 1)
        if ":" in auth:
            username, password = auth.split(":", 1)
        else:
            username, password = auth, ""

    parts = rest.split(":")
    if len(parts) == 2:
        host, port_s = parts
    elif len(parts) == 4:
        host, port_s, username, password = parts
    else:
        raise ValueError(
            f"formato no reconocido: {raw!r}. "
            "Usa ip:puerto | ip:puerto:usuario:clave | http://usuario:clave@ip:puerto"
        )

    host = host.strip()
    if not host:
        raise ValueError(f"host vacío en {raw!r}")
    try:
        port = int(port_s)
    except (TypeError, ValueError):
        raise ValueError(f"puerto inválido en {raw!r}") from None
    if not (1 <= port <= 65535):
        raise ValueError(f"puerto fuera de rango en {raw!r}")

    return Proxy(
        raw=s,
        scheme=scheme,
        host=host,
        port=port,
        username=username or None,
        password=password or None,
    )


@dataclass
class Attempt:
    """Resultado de intentar una petición a través de una IP."""

    proxy: str
    status_code: Optional[int] = None
    error: str = ""
    elapsed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proxy": self.proxy,
            "status_code": self.status_code,
            "error": self.error,
            "elapsed_ms": round(self.elapsed * 1000, 1),
        }


@dataclass
class RotationResult:
    """Resultado agregado de una petición con rotación automática."""

    ok: bool = False
    status_code: Optional[int] = None
    body: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    proxy_used: Optional[str] = None
    attempts: List[Attempt] = field(default_factory=list)
    elapsed_total: float = 0.0
    error: str = ""
    body_truncated: bool = False

    @property
    def distinct_ips_tried(self) -> int:
        """Número de IPs distintas que se probaron en esta petición."""
        return len(self.attempts)

    def to_dict(self, include_body: bool = True) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "ok": self.ok,
            "status_code": self.status_code,
            "proxy_used": self.proxy_used,
            "distinct_ips_tried": self.distinct_ips_tried,
            "attempts": [a.to_dict() for a in self.attempts],
            "elapsed_total_ms": round(self.elapsed_total * 1000, 1),
            "error": self.error,
        }
        if include_body:
            d["body"] = self.body
            d["body_truncated"] = self.body_truncated
        return d


# --------------------------------------------------------------------------- #
# Rotador
# --------------------------------------------------------------------------- #

class ProxyRotator:
    """
    Pool de proxies con rotación automática y auto-recovery.

    Parámetros
    ----------
    proxies:
        Lista inicial de proxies (cadenas en cualquier formato aceptado por
        :func:`parse_proxy` o instancias :class:`Proxy`).
    strategy:
        round_robin | random | least_used.
    cooldown_seconds:
        Tras un fallo, la IP queda fuera de rotación este tiempo (auto-recovery).
    dead_revive_seconds:
        Una IP DEAD se re-testea automáticamente tras este tiempo.
        Con 0 las IPs DEAD no se recuperan solas.
    max_consecutive_failures:
        Fallos seguidos necesarios para declarar una IP DEAD.
    request_timeout:
        Timeout por defecto (segundos) de cada intento.
    max_rotations:
        Máximo de IPs distintas a probar por petición (por defecto 99,
        aunque el pool sea menor nunca se intentará más de lo disponible).
    retry_status:
        Códigos HTTP que provocan rotación inmediata (por defecto 403/429/503).
        Cualquier otro código (404, 500...) se devuelve tal cual: la IP
        funcionó, el problema es del recurso.
    polite_delay:
        Pausa (segundos) entre intentos de una misma petición. Recomendado
        >= 1.0 para sitios con anti-bot.
    max_pool_size:
        Límite duro del pool (99 por defecto, según requisito).
    """

    def __init__(
        self,
        proxies: Iterable[Any] = (),
        *,
        strategy: str = RotationStrategy.ROUND_ROBIN.value,
        cooldown_seconds: float = 300.0,
        dead_revive_seconds: float = 3600.0,
        max_consecutive_failures: int = 5,
        request_timeout: float = 25.0,
        max_rotations: int = MAX_POOL_SIZE,
        retry_status: Sequence[int] = RETRYABLE_STATUS_DEFAULT,
        polite_delay: float = 0.0,
        max_pool_size: int = MAX_POOL_SIZE,
    ) -> None:
        self._lock = threading.RLock()
        self._proxies: "OrderedDict[str, Proxy]" = OrderedDict()
        self._rr_counter = itertools.count()

        self.max_pool_size = int(max_pool_size)
        if self.max_pool_size < 1:
            raise ValueError("max_pool_size debe ser >= 1")
        self.strategy = RotationStrategy(strategy)
        self.cooldown_seconds = float(cooldown_seconds)
        self.dead_revive_seconds = float(dead_revive_seconds)
        self.max_consecutive_failures = max(1, int(max_consecutive_failures))
        self.request_timeout = float(request_timeout)
        self.max_rotations = max(1, int(max_rotations))
        self.retry_status = tuple(retry_status)
        self.polite_delay = float(polite_delay)

        for raw in proxies:
            self.add(raw)

    # ------------------------------------------------------------------ #
    # Gestión del pool
    # ------------------------------------------------------------------ #

    def add(self, raw: Any, *, replace: bool = True) -> Proxy:
        """Añade un proxy. Lanza PoolFullError o DuplicateProxyError."""
        p = raw if isinstance(raw, Proxy) else parse_proxy(raw)
        with self._lock:
            existing = self._proxies.get(p.id)
            if existing is not None:
                if not replace:
                    raise DuplicateProxyError(f"ya existe {p.id}")
                # conserva estadísticas históricas
                p.total_requests = existing.total_requests
                p.successes = existing.successes
                p.failures = existing.failures
                p.total_latency = existing.total_latency
                p.status = existing.status
                p.consecutive_failures = existing.consecutive_failures
                p.last_used = existing.last_used
                p.last_failure_at = existing.last_failure_at
                p.cooldown_until = existing.cooldown_until
                p.last_error = existing.last_error
                p.added_at = existing.added_at
                self._proxies[p.id] = p
                return p
            if len(self._proxies) >= self.max_pool_size:
                raise PoolFullError(
                    f"pool lleno: máximo {self.max_pool_size} IPs (límite de rotación)"
                )
            self._proxies[p.id] = p
            return p

    def add_many(self, raws: Iterable[Any]) -> Tuple[List[Proxy], List[Dict[str, str]]]:
        """Añade en lote. Devuelve (añadidos, errores:[{raw, error}])."""
        added: List[Proxy] = []
        errors: List[Dict[str, str]] = []
        for raw in raws:
            try:
                added.append(self.add(raw))
            except (ProxyRotatorError, ValueError) as e:
                errors.append({"raw": str(raw), "error": str(e)})
        return added, errors

    def remove(self, proxy_id: str) -> bool:
        """Elimina por id (host:puerto). True si existía."""
        with self._lock:
            return self._proxies.pop(proxy_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._proxies.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._proxies)

    def get(self, proxy_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._sweep()
            p = self._proxies.get(proxy_id)
            return p.to_dict() if p else None

    def list(self) -> List[Dict[str, Any]]:
        """Snapshot del estado de todos los proxies (para API/dashboard)."""
        with self._lock:
            self._sweep()
            return [p.to_dict() for p in self._proxies.values()]

    def stats(self) -> Dict[str, Any]:
        """Agregados del pool."""
        with self._lock:
            self._sweep()
            ps = list(self._proxies.values())
            total_req = sum(p.total_requests for p in ps)
            total_ok = sum(p.successes for p in ps)
            by_status = {s.value: 0 for s in ProxyStatus}
            for p in ps:
                by_status[p.status.value] += 1
            return {
                "pool_size": len(ps),
                "max_pool_size": self.max_pool_size,
                "by_status": by_status,
                "total_requests": total_req,
                "total_successes": total_ok,
                "total_failures": total_req - total_ok,
                "success_rate": round(total_ok / total_req, 4) if total_req else 0.0,
            }

    def config(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "strategy": self.strategy.value,
                "cooldown_seconds": self.cooldown_seconds,
                "dead_revive_seconds": self.dead_revive_seconds,
                "max_consecutive_failures": self.max_consecutive_failures,
                "request_timeout": self.request_timeout,
                "max_rotations": self.max_rotations,
                "retry_status": list(self.retry_status),
                "polite_delay": self.polite_delay,
                "max_pool_size": self.max_pool_size,
            }

    def update_config(
        self,
        *,
        strategy: Optional[str] = None,
        cooldown_seconds: Optional[float] = None,
        dead_revive_seconds: Optional[float] = None,
        max_consecutive_failures: Optional[int] = None,
        request_timeout: Optional[float] = None,
        max_rotations: Optional[int] = None,
        retry_status: Optional[Sequence[int]] = None,
        polite_delay: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Actualiza parámetros en caliente (validando tipos/rangos)."""
        with self._lock:
            if strategy is not None:
                self.strategy = RotationStrategy(strategy)
            if cooldown_seconds is not None:
                if cooldown_seconds < 0:
                    raise ValueError("cooldown_seconds >= 0")
                self.cooldown_seconds = float(cooldown_seconds)
            if dead_revive_seconds is not None:
                if dead_revive_seconds < 0:
                    raise ValueError("dead_revive_seconds >= 0")
                self.dead_revive_seconds = float(dead_revive_seconds)
            if max_consecutive_failures is not None:
                self.max_consecutive_failures = max(1, int(max_consecutive_failures))
            if request_timeout is not None:
                if request_timeout <= 0:
                    raise ValueError("request_timeout > 0")
                self.request_timeout = float(request_timeout)
            if max_rotations is not None:
                if max_rotations < 1:
                    raise ValueError("max_rotations >= 1")
                self.max_rotations = int(max_rotations)
            if retry_status is not None:
                self.retry_status = tuple(int(s) for s in retry_status)
            if polite_delay is not None:
                if polite_delay < 0:
                    raise ValueError("polite_delay >= 0")
                self.polite_delay = float(polite_delay)
            return self.config()

    def reset(self, *, revive_dead: bool = True, clear_stats: bool = False) -> None:
        """Revive proxies y opcionalmente borra estadísticas."""
        with self._lock:
            for p in self._proxies.values():
                if revive_dead:
                    p.status = ProxyStatus.UNTESTED
                    p.consecutive_failures = 0
                    p.cooldown_until = 0.0
                    p.last_error = ""
                if clear_stats:
                    p.total_requests = 0
                    p.successes = 0
                    p.failures = 0
                    p.total_latency = 0.0
                    p.last_used = 0.0

    # ------------------------------------------------------------------ #
    # Selección / estado (auto-recovery)
    # ------------------------------------------------------------------ #

    def _revive_if_due(self, p: Proxy, now: float) -> None:
        """Auto-recovery perezoso: se ejecuta al seleccionar, sin hilos extra."""
        if p.status == ProxyStatus.COOLDOWN and now >= p.cooldown_until:
            p.status = ProxyStatus.ACTIVE
            p.consecutive_failures = 0
            p.last_error = ""
        elif (
            p.status == ProxyStatus.DEAD
            and self.dead_revive_seconds > 0
            and now >= p.last_failure_at + self.dead_revive_seconds
        ):
            p.status = ProxyStatus.UNTESTED
            p.consecutive_failures = 0
            p.last_error = ""

    def _sweep(self) -> None:
        """Aplica el auto-recovery a todo el pool (bajo lock, sin hilos)."""
        now = time.time()
        for p in self._proxies.values():
            self._revive_if_due(p, now)

    def _pick(self, exclude_ids: set) -> Optional[Proxy]:
        """Elige el siguiente proxy disponible según la estrategia."""
        now = time.time()
        candidates: List[Proxy] = []
        for p in self._proxies.values():
            self._revive_if_due(p, now)
            if p.id in exclude_ids:
                continue
            if p.status in (ProxyStatus.ACTIVE, ProxyStatus.UNTESTED):
                candidates.append(p)
        if not candidates:
            return None

        if self.strategy == RotationStrategy.RANDOM:
            return random.choice(candidates)
        if self.strategy == RotationStrategy.LEAST_USED:
            return min(candidates, key=lambda p: (p.total_requests, p.added_at))
        # ROUND_ROBIN: la disponible usada hace más tiempo (turno justo),
        # con desempate estable por orden de inserción.
        return min(candidates, key=lambda p: (p.last_used, p.added_at))

    def _mark_failure(self, p: Proxy, reason: str) -> None:
        now = time.time()
        p.total_requests += 1
        p.failures += 1
        p.consecutive_failures += 1
        p.last_used = now
        p.last_failure_at = now
        p.last_error = reason[:300]
        if p.consecutive_failures >= self.max_consecutive_failures:
            p.status = ProxyStatus.DEAD
            p.cooldown_until = now + self.dead_revive_seconds
        else:
            p.status = ProxyStatus.COOLDOWN
            p.cooldown_until = now + self.cooldown_seconds

    def _mark_success(self, p: Proxy, latency: float) -> None:
        now = time.time()
        p.total_requests += 1
        p.successes += 1
        p.total_latency += latency
        p.consecutive_failures = 0
        p.last_used = now
        p.last_error = ""
        p.status = ProxyStatus.ACTIVE
        p.cooldown_until = 0.0

    # ------------------------------------------------------------------ #
    # API de integración externa (Selenium, cloudscraper, flujos propios)
    # ------------------------------------------------------------------ #

    def next_proxy(self, exclude: Sequence[str] = ()) -> Optional[Dict[str, Any]]:
        """
        Reserva y devuelve el siguiente proxy disponible SIN ejecutar la
        petición aquí. Pensado para proyectos que hacen el HTTP por su cuenta
        (p. ej. configurar un WebDriver con ese proxy).

        Devuelve {"id", "url", "host", "port", "scheme"} o None si no hay
        IPs disponibles. El llamante DEBE reportar el resultado con
        :meth:`report_success` / :meth:`report_failure` para que el
        auto-recovery funcione.
        """
        with self._lock:
            p = self._pick(set(exclude))
            if p is None:
                return None
            p.last_used = time.time()
            return {
                "id": p.id,
                "url": p.url,
                "host": p.host,
                "port": p.port,
                "scheme": p.scheme,
                "username": p.username,
                "password": p.password,
            }

    def report_success(self, proxy_id: str, latency: Optional[float] = None) -> None:
        with self._lock:
            p = self._proxies.get(proxy_id)
            if p is not None:
                self._mark_success(p, latency if latency is not None else 0.0)

    def report_failure(self, proxy_id: str, reason: str = "manual") -> None:
        with self._lock:
            p = self._proxies.get(proxy_id)
            if p is not None:
                self._mark_failure(p, reason)

    # ------------------------------------------------------------------ #
    # Núcleo: petición con rotación
    # ------------------------------------------------------------------ #

    def request(
        self,
        method: str,
        url: str,
        *,
        client: str = "requests",
        session: Any = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Any = None,
        json_payload: Any = None,
        max_rotations: Optional[int] = None,
        timeout: Optional[float] = None,
        polite_delay: Optional[float] = None,
        verify: bool = True,
        follow_redirects: bool = True,
        body_limit: int = 300_000,
        **extra: Any,
    ) -> RotationResult:
        """
        Ejecuta ``method url`` rotando IPs hasta tener éxito o agotar el pool.

        - `session` (opcional): un objeto ``requests.Session`` compatible
          (incluido cloudscraper). Se usan sus cabeceras/cookies y se le pasa
          el proxy por-petición, sin contaminar la sesión.
        - `client`: "requests" (por defecto) o "httpx".
        - `max_rotations`: IPs distintas a probar (por defecto el configurado,
          99); nunca se probarán más de las disponibles en el pool.
        - Códigos en `retry_status` (403/429/503) => rota a la siguiente IP.
          Otros códigos (404, 500...) se devuelven con ok=True: la IP funcionó.
        - `polite_delay`: pausa entre intentos (segundos). Si es None usa la
          del configurador global.
        """
        rot = self.max_rotations if max_rotations is None else max(1, int(max_rotations))
        delay = self.polite_delay if polite_delay is None else float(polite_delay)
        eff_timeout = float(timeout) if timeout else self.request_timeout

        result = RotationResult(ok=False)
        tried: set = set()
        last_status: Optional[int] = None
        t0 = time.time()

        for _ in range(rot):
            with self._lock:
                proxy = self._pick(exclude_ids=tried)
            if proxy is None:
                break
            tried.add(proxy.id)

            if delay and result.attempts:
                time.sleep(delay)

            attempt = Attempt(proxy=proxy.masked())
            t1 = time.time()
            try:
                status, resp_headers, body, truncated = self._do_request(
                    client,
                    session,
                    method,
                    url,
                    proxy,
                    headers=headers,
                    params=params,
                    data=data,
                    json_payload=json_payload,
                    timeout=eff_timeout,
                    verify=verify,
                    follow_redirects=follow_redirects,
                    body_limit=body_limit,
                    **extra,
                )
            except Exception as exc:  # transporte, timeout, proxy caído...
                attempt.elapsed = time.time() - t1
                attempt.error = f"{type(exc).__name__}: {exc}"[:300]
                with self._lock:
                    self._mark_failure(proxy, attempt.error)
                result.attempts.append(attempt)
                continue

            attempt.elapsed = time.time() - t1
            attempt.status_code = status

            if status in self.retry_status:
                attempt.error = f"HTTP {status}: IP bloqueada/limitada, rotando"
                with self._lock:
                    self._mark_failure(proxy, attempt.error)
                result.attempts.append(attempt)
                last_status = status
                continue

            with self._lock:
                self._mark_success(proxy, attempt.elapsed)

            result.ok = True
            result.status_code = status
            result.body = body
            result.body_truncated = truncated
            result.headers = resp_headers
            result.proxy_used = proxy.masked()
            result.attempts.append(attempt)
            result.elapsed_total = time.time() - t0
            return result

        result.elapsed_total = time.time() - t0
        if not result.attempts:
            result.error = "no hay IPs disponibles en el pool (todas en cooldown/dead o pool vacío)"
        else:
            extra_msg = f" (último estado HTTP {last_status})" if last_status else ""
            result.error = (
                f"agotadas {len(tried)} IP(s) distintas sin éxito{extra_msg}"
            )
        return result

    # -- adaptadores HTTP ------------------------------------------------ #

    def _do_request(
        self,
        client: str,
        session: Any,
        method: str,
        url: str,
        proxy: Proxy,
        *,
        headers: Optional[Dict[str, str]],
        params: Optional[Dict[str, Any]],
        data: Any,
        json_payload: Any,
        timeout: float,
        verify: bool,
        follow_redirects: bool,
        body_limit: int,
        **extra: Any,
    ) -> Tuple[int, Dict[str, str], Optional[str], bool]:
        """Devuelve (status, headers, body(truncado), body_truncated)."""
        proxy_map = {"http://": proxy.url, "https://": proxy.url}

        if client == "requests":
            requests = self._import("requests")
            if session is not None:
                resp = session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json_payload,
                    proxies=proxy_map,
                    timeout=timeout,
                    verify=verify,
                    allow_redirects=follow_redirects,
                    **extra,
                )
            else:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json_payload,
                    proxies=proxy_map,
                    timeout=timeout,
                    verify=verify,
                    allow_redirects=follow_redirects,
                    **extra,
                )
            body = resp.text
            truncated = len(body) > body_limit
            return resp.status_code, dict(resp.headers), body[:body_limit], truncated

        if client == "httpx":
            httpx = self._import("httpx")
            client_kwargs: Dict[str, Any] = {"timeout": timeout, "verify": verify}
            try:
                http_client = httpx.Client(proxy=proxy.url, **client_kwargs)
            except TypeError:  # httpx antiguo usa proxies=
                http_client = httpx.Client(proxies=proxy_map, **client_kwargs)
            try:
                resp = http_client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json_payload,
                    follow_redirects=follow_redirects,
                    **extra,
                )
                body = resp.text
                truncated = len(body) > body_limit
                return (
                    resp.status_code,
                    dict(resp.headers),
                    body[:body_limit],
                    truncated,
                )
            finally:
                http_client.close()

        raise ProxyRotatorError(
            f"cliente no soportado: {client!r} (usa 'requests' o 'httpx')"
        )

    @staticmethod
    def _import(name: str):
        try:
            return __import__(name)
        except ImportError:
            raise ProxyRotatorError(
                f"falta la dependencia {name!r}: pip install {name}"
            ) from None

    # -- health check ----------------------------------------------------- #

    def health_check(
        self,
        url: str = "https://httpbin.org/ip",
        *,
        proxy_ids: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
        client: str = "requests",
    ) -> List[Dict[str, Any]]:
        """
        Prueba cada proxy (o los indicados) contra `url`. Un éxito reviva el
        proxy aunque estuviera DEAD/COOLDOWN. Devuelve por proxy: ok,
        status_code, latencia e IP de salida detectada cuando es posible.
        """
        with self._lock:
            if proxy_ids:
                targets = [self._proxies[pid] for pid in proxy_ids if pid in self._proxies]
            else:
                targets = list(self._proxies.values())

        results: List[Dict[str, Any]] = []
        for p in targets:
            t0 = time.time()
            try:
                status, _h, body, _t = self._do_request(
                    client,
                    None,
                    "GET",
                    url,
                    p,
                    headers=None,
                    params=None,
                    data=None,
                    json_payload=None,
                    timeout=timeout or self.request_timeout,
                    verify=True,
                    follow_redirects=True,
                    body_limit=5_000,
                )
                elapsed = time.time() - t0
                ok = 200 <= status < 400
                exit_ip = None
                if ok and body:
                    try:
                        import json as _json

                        exit_ip = _json.loads(body).get("origin")
                    except Exception:
                        exit_ip = None
                if ok:
                    # éxito manual: revive y limpia fallos
                    with self._lock:
                        self._mark_success(p, elapsed)
                else:
                    with self._lock:
                        self._mark_failure(p, f"health check HTTP {status}")
                results.append(
                    {
                        "id": p.id,
                        "ok": ok,
                        "status_code": status,
                        "latency_ms": round(elapsed * 1000, 1),
                        "exit_ip": exit_ip,
                        "error": "" if ok else f"HTTP {status}",
                    }
                )
            except Exception as exc:
                elapsed = time.time() - t0
                err = f"{type(exc).__name__}: {exc}"[:300]
                with self._lock:
                    self._mark_failure(p, err)
                results.append(
                    {
                        "id": p.id,
                        "ok": False,
                        "status_code": None,
                        "latency_ms": round(elapsed * 1000, 1),
                        "exit_ip": None,
                        "error": err,
                    }
                )
        return results
