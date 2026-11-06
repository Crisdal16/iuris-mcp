"""
ip_rotator.storage
==================

Persistencia del pool:

    proxies.txt   -> lista de proxies (una por línea, formatos del parse_proxy,
                     comentarios con # y líneas en blanco permitidas).
    state.json    -> estadísticas/estado por proxy para sobrevivir reinicios.

Uso:
    store = ProxyStore("/ruta/al/directorio")
    rot = ProxyRotator()
    n = store.load_into(rot)          # carga lista + estado
    ...
    store.save_from(rot)              # guarda lista y estado
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List

from .rotator import Proxy, ProxyRotator, ProxyStatus

__all__ = ["ProxyStore"]

_STATE_FIELDS = (
    "status",
    "consecutive_failures",
    "total_requests",
    "successes",
    "failures",
    "total_latency",
    "last_used",
    "last_failure_at",
    "cooldown_until",
    "last_error",
    "added_at",
)


class ProxyStore:
    """Guarda/carga la lista de proxies y sus estadísticas en disco."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        self.proxies_file = os.path.join(base_dir, "proxies.txt")
        self.state_file = os.path.join(base_dir, "state.json")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Carga
    # ------------------------------------------------------------------ #

    def read_list(self) -> List[str]:
        """Lee proxies.txt y devuelve las líneas no comentadas."""
        if not os.path.exists(self.proxies_file):
            return []
        out: List[str] = []
        with open(self.proxies_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
        return out

    def load_into(self, rotator: ProxyRotator, *, apply_state: bool = True) -> int:
        """
        Carga la lista en el rotador y, si procede, restaura estadísticas
        desde state.json. Devuelve cuántos proxies se cargaron.
        """
        raws = self.read_list()
        for raw in raws:
            try:
                rotator.add(raw)
            except Exception:
                continue  # duplicados / pool lleno: no interrumpir el arranque

        if apply_state and os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as fh:
                    state = json.load(fh)
                self._apply_state(rotator, state)
            except Exception:
                pass
        return len(rotator)

    @staticmethod
    def _apply_state(rotator: ProxyRotator, state: Dict[str, Any]) -> None:
        for pid, fields in (state.get("proxies") or {}).items():
            # restaurar solo si el proxy sigue en la lista
            current = rotator.get(pid)
            if current is None:
                continue
            with rotator._lock:  # noqa: SLF001 — misma librería
                p = rotator._proxies.get(pid)
                if p is None:
                    continue
                if fields.get("status") == ProxyStatus.DEAD.value:
                    # al reiniciar, no arrastrar "dead": dar una oportunidad
                    p.status = ProxyStatus.UNTESTED
                    p.consecutive_failures = 0
                elif fields.get("status") == ProxyStatus.COOLDOWN.value:
                    cooldown_until = float(fields.get("cooldown_until", 0) or 0)
                    if cooldown_until > time.time():
                        p.status = ProxyStatus.COOLDOWN
                        p.cooldown_until = cooldown_until
                for f in ("total_requests", "successes", "failures",
                          "total_latency", "last_used", "last_failure_at",
                          "added_at"):
                    if f in fields:
                        setattr(p, f, fields[f])
                p.last_error = fields.get("last_error", "") or ""

    # ------------------------------------------------------------------ #
    # Guardado
    # ------------------------------------------------------------------ #

    def save_from(self, rotator: ProxyRotator) -> None:
        """Escribe proxies.txt (sin comentarios) y state.json."""
        with self._lock:
            os.makedirs(self.base_dir, exist_ok=True)

            with rotator._lock:  # noqa: SLF001 — misma librería
                proxies = list(rotator._proxies.values())

            lines = [
                f"{p.scheme}://{p.username}:{p.password or ''}@{p.host}:{p.port}"
                if p.username
                else f"{p.host}:{p.port}"
                for p in proxies
            ]
            tmp = self.proxies_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + ("\n" if lines else ""))
            os.replace(tmp, self.proxies_file)

            state = {
                "saved_at": time.time(),
                "proxies": {
                    p.id: {f: getattr(p, f) for f in _STATE_FIELDS}
                    for p in proxies
                },
            }
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.state_file)

    def export_template(self) -> None:
        """Crea proxies.txt con documentación si no existe todavía."""
        if os.path.exists(self.proxies_file):
            return
        os.makedirs(self.base_dir, exist_ok=True)
        template = """# proxies.txt — un proxy por línea (líneas con # se ignoran)
#
# Formatos aceptados:
#   ip:puerto
#   ip:puerto:usuario:clave
#   http://ip:puerto
#   http://usuario:clave@ip:puerto
#
# Ejemplos (INVÁLIDOS, borra el # y sustituye por tus IPs reales):
# 203.0.113.10:8080
# 203.0.113.11:8080:miusuario:miclave
"""
        with open(self.proxies_file, "w", encoding="utf-8") as fh:
            fh.write(template)
