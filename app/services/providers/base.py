"""Abstract provider client definitions used by the reporting pipeline."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

from ...schemas import ProviderDataset, ReportSpec


class ProviderError(Exception):
    """Base error for provider specific failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when registry entries are malformed or missing secrets."""


class ProviderRequestError(ProviderError):
    """Raised when the upstream provider rejects a request."""


@dataclass(slots=True)
class SignedRequest:
    """Container holding the payload and headers sent to the provider."""

    payload: Mapping[str, Any]
    headers: Mapping[str, str] | None = None


class BaseProviderClient(ABC):
    """Common interface for provider implementations."""

    def __init__(self, provider_id: str, config: Mapping[str, Any] | None = None, secrets: Mapping[str, Any] | None = None) -> None:
        self.provider_id = provider_id
        self.config = dict(config or {})
        self.secrets = dict(secrets or {})

    async def fetch(self, spec: ReportSpec) -> ProviderDataset:
        """Fetch and normalize data for a report spec."""

        payload = self.build_payload(spec)
        signed_request = self.sign_request(payload)
        response = await self.dispatch(signed_request, spec)
        dataset = self.parse_response(response, spec)
        return dataset

    @abstractmethod
    def build_payload(self, spec: ReportSpec) -> Mapping[str, Any]:
        """Translate the normalized spec into provider-specific parameters."""

    def sign_request(self, payload: Mapping[str, Any]) -> SignedRequest:
        """Attach auth headers for the provider call."""

        return SignedRequest(payload=payload, headers={})

    @abstractmethod
    async def dispatch(self, request: SignedRequest, spec: ReportSpec) -> Mapping[str, Any]:
        """Send the HTTP request to the provider and return a JSON payload."""

    @abstractmethod
    def parse_response(self, payload: Mapping[str, Any], spec: ReportSpec) -> ProviderDataset:
        """Normalize provider JSON into a ProviderDataset."""
