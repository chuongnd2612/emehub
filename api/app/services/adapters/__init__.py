"""Provider adapters — registry and factory.

Concrete adapters live in their own modules and register themselves on import.
Callers resolve one by provider kind through :func:`get_adapter`; nothing outside
this package should import a concrete adapter class by name.

The registry is populated lazily on first use so importing
``app.services.adapters`` during app bootstrap cannot create an import cycle
through ``app.services.connection_service``.
"""

from __future__ import annotations

import httpx

from app.services.adapters.base import (
    NormalizedTicket,
    ProviderAdapter,
    ProviderError,
    scrub,
)

_REGISTRY: dict[str, type[ProviderAdapter]] = {}

#: Whether the built-in adapter modules have been imported. A separate flag and
#: not ``bool(_REGISTRY)``: importing *one* adapter module — which anything
#: holding a direct reference to a concrete adapter does — registers that kind and
#: makes the registry non-empty, and an emptiness check then treats the job as
#: done. Every other provider is missing from that point on, with the symptom
#: appearing much later as "No adapter registered for provider 'github'" on a
#: connection that is perfectly well configured.
_LOADED = False


def register(kind: str, cls: type[ProviderAdapter]) -> None:
    """Register ``cls`` as the adapter for ``kind``. Called at module import."""
    _REGISTRY[kind] = cls


def _load_builtin() -> None:
    """Import every built-in adapter module, once, for its ``register()`` call."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from app.services.adapters import azure_devops, github, jira  # noqa: F401


def registered_kinds() -> tuple[str, ...]:
    """Every kind an adapter exists for. Used by the tests that assert the
    adapter registry and the model's kind list have not drifted apart."""
    _load_builtin()
    return tuple(_REGISTRY)


def get_adapter(
    kind: str,
    config: dict,
    secrets: dict,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProviderAdapter:
    """Instantiate the adapter for ``kind`` with decrypted config and secrets.

    Args:
        kind: ``azure_devops`` | ``github`` | ``jira``.
        config: non-secret adapter fields.
        secrets: decrypted secrets, keyed ``pat``.
        transport: ``httpx`` transport override. **Tests only.**

    Raises:
        ProviderError: no adapter is registered for ``kind``.
    """
    _load_builtin()
    cls = _REGISTRY.get(kind)
    if cls is None:
        raise ProviderError(f"No adapter registered for provider '{kind}'")
    return cls(config=config, secrets=secrets, transport=transport)


__all__ = [
    "NormalizedTicket",
    "ProviderAdapter",
    "ProviderError",
    "get_adapter",
    "register",
    "registered_kinds",
    "scrub",
]
