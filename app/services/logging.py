"""Request-scoped logging helpers and in-memory log store."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, MutableMapping


class RequestLogStore:
    """Lightweight in-memory store so engineers can inspect milestones."""

    def __init__(self) -> None:
        self._records: Dict[str, List[Mapping[str, Any]]] = {}

    def append(self, request_id: str, entry: Mapping[str, Any]) -> None:
        self._records.setdefault(request_id, []).append(entry)

    def get(self, request_id: str) -> List[Mapping[str, Any]]:
        return list(self._records.get(request_id, []))

    def clear(self) -> None:
        self._records.clear()


request_log_store = RequestLogStore()


@dataclass
class RequestContext:
    """State bag that injects IDs into every log line for a request."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    provider_id: str | None = None
    interpreter: str | None = None
    downstream_requests: MutableMapping[str, str] = field(default_factory=dict)
    _store: RequestLogStore = field(default=request_log_store, repr=False)

    def with_provider(self, provider_id: str | None) -> "RequestContext":
        if provider_id:
            self.provider_id = provider_id
        return self

    def with_interpreter(self, interpreter: str | None) -> "RequestContext":
        if interpreter:
            self.interpreter = interpreter
        return self

    def register_downstream(self, name: str, identifier: str) -> None:
        if name and identifier:
            self.downstream_requests[name] = identifier

    def extra(self, **fields: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"request_id": self.request_id}
        if self.provider_id:
            payload["provider_id"] = self.provider_id
        if self.interpreter:
            payload["interpreter"] = self.interpreter
        if self.downstream_requests:
            payload["downstream_request_ids"] = dict(self.downstream_requests)
        for key, value in fields.items():
            if value is not None:
                payload[key] = value
        return payload

    def log(
        self,
        logger: logging.Logger,
        level: int,
        message: str,
        *,
        exc_info: bool | BaseException | None = None,
        stack_info: bool = False,
        **fields: Any,
    ) -> None:
        extra_payload = self.extra(**fields)
        logger.log(level, message, extra=extra_payload, exc_info=exc_info, stack_info=stack_info)
        self._store.append(
            self.request_id,
            {
                "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
                "level": logging.getLevelName(level),
                "message": message,
                "extra": extra_payload,
            },
        )

    def debug(self, logger: logging.Logger, message: str, **fields: Any) -> None:
        self.log(logger, logging.DEBUG, message, **fields)

    def info(self, logger: logging.Logger, message: str, **fields: Any) -> None:
        self.log(logger, logging.INFO, message, **fields)

    def warning(self, logger: logging.Logger, message: str, *, exc_info: bool | BaseException | None = None, **fields: Any) -> None:
        self.log(logger, logging.WARNING, message, exc_info=exc_info, **fields)

    def error(self, logger: logging.Logger, message: str, *, exc_info: bool | BaseException | None = None, **fields: Any) -> None:
        self.log(logger, logging.ERROR, message, exc_info=exc_info, **fields)

    def exception(self, logger: logging.Logger, message: str, **fields: Any) -> None:
        self.log(logger, logging.ERROR, message, exc_info=True, **fields)


__all__ = ["RequestContext", "request_log_store", "RequestLogStore"]
