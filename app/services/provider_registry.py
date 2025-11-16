"""Registry for provider specifications derived from SatSource metadata."""
from __future__ import annotations

from typing import Dict, Optional

from ..schemas import ProviderSpec


class ProviderRegistry:
    """Simple in-memory registry that can later be swapped with persistent storage."""

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderSpec] = {}

    def upsert(self, spec: ProviderSpec) -> ProviderSpec:
        """Create or update the spec for a provider."""

        self._providers[spec.provider_id] = spec
        return spec

    def get(self, provider_id: str) -> Optional[ProviderSpec]:
        return self._providers.get(provider_id)

    def clear(self) -> None:
        self._providers.clear()


provider_registry = ProviderRegistry()
"""Module-level registry instance used by the API layer."""
