"""Factory responsible for instantiating provider clients from the registry."""
from __future__ import annotations

import logging
from typing import Dict, Mapping

from fastapi import HTTPException, status

from .base import BaseProviderClient, ProviderConfigurationError, ProviderRequestError
from .registry import ProviderRegistryEntry, load_default_registry

logger = logging.getLogger(__name__)


class ProviderClientFactory:
    """Resolve provider IDs into configured client instances."""

    def __init__(self, registry: Mapping[str, ProviderRegistryEntry] | None = None) -> None:
        self._registry: Dict[str, ProviderRegistryEntry] = dict(registry or load_default_registry())

    def get_client(self, provider_id: str) -> BaseProviderClient:
        provider_id = (provider_id or "").strip()
        if not provider_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="provider_id is required")
        entry = self._registry.get(provider_id)
        if not entry:
            logger.warning("unknown provider requested", extra={"provider_id": provider_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
        try:
            client = entry.client(provider_id=provider_id, config=entry.config, secrets=entry.secrets)
        except ProviderConfigurationError as exc:
            logger.exception("provider misconfigured", extra={"provider_id": provider_id})
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return client


__all__ = ["ProviderClientFactory", "ProviderConfigurationError", "ProviderRequestError"]
