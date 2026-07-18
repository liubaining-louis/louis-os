from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from atlas.opportunity_discovery import OpportunitySignal


Fetcher = Callable[[Request, float], bytes]


@dataclass(frozen=True)
class HttpSourcePolicy:
    allowed_hosts: tuple[str, ...]
    timeout_seconds: float = 10.0
    maximum_bytes: int = 1_000_000
    user_agent: str = "Louis-OS-ATLAS/1.0"

    def validate(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("allowed_hosts is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")
        if not self.user_agent.strip():
            raise ValueError("user_agent is required")
        for host in self.allowed_hosts:
            if not host.strip() or "/" in host or ":" in host:
                raise ValueError("allowed_hosts must contain bare host names")


class HttpJsonOpportunitySource:
    """Collect opportunity signals from a controlled HTTPS JSON endpoint.

    The endpoint must return either a JSON list or an object containing an
    ``items`` list. Network access is bounded by an explicit host allowlist,
    timeout and response-size limit. No external action is performed.
    """

    def __init__(
        self,
        *,
        source_name: str,
        endpoint_url: str,
        policy: HttpSourcePolicy,
        fetcher: Fetcher | None = None,
    ) -> None:
        if not source_name.strip():
            raise ValueError("source_name is required")
        self.source_name = source_name
        self.endpoint_url = endpoint_url
        self.policy = policy
        self.policy.validate()
        self._validate_endpoint()
        self._fetcher = fetcher or self._default_fetcher

    def collect(self) -> Iterable[OpportunitySignal]:
        request = Request(
            self.endpoint_url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.policy.user_agent,
            },
            method="GET",
        )
        raw = self._fetcher(request, self.policy.timeout_seconds)
        if len(raw) > self.policy.maximum_bytes:
            raise ValueError("source response exceeds maximum_bytes")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("source response must be valid UTF-8 JSON") from exc

        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("source JSON must be a list or contain an items list")

        signals: list[OpportunitySignal] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise ValueError(f"source item {index} must be an object")
            signals.append(self._to_signal(item, index))
        return signals

    def _validate_endpoint(self) -> None:
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("endpoint_url must be an absolute HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("endpoint_url must not contain credentials")
        if parsed.hostname not in self.policy.allowed_hosts:
            raise ValueError("endpoint host is not allowlisted")

    def _to_signal(self, item: Mapping[str, object], index: int) -> OpportunitySignal:
        source_url = str(item.get("source_url") or self.endpoint_url)
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"source item {index} has invalid source_url")

        return OpportunitySignal(
            source_id=str(item.get("source_id") or f"{self.source_name}-{index}"),
            source_url=source_url,
            title=str(item.get("title") or ""),
            problem=str(item.get("problem") or ""),
            target_customer=str(item.get("target_customer") or ""),
            proposed_offer=str(item.get("proposed_offer") or ""),
            expected_value=self._score(item, "expected_value", index),
            autonomy=self._score(item, "autonomy", index),
            learning_value=self._score(item, "learning_value", index),
            speed=self._score(item, "speed", index),
            human_dependency=self._score(item, "human_dependency", index),
            cost=self._score(item, "cost", index),
            risk=self._score(item, "risk", index),
            observed_at=str(item.get("observed_at") or ""),
        )

    @staticmethod
    def _score(item: Mapping[str, object], name: str, index: int) -> float:
        value = item.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"source item {index} field {name} must be numeric")
        return float(value)

    def _default_fetcher(self, request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:  # nosec B310: host is explicitly allowlisted
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "text/json"}:
                raise ValueError("source response content type must be JSON")
            body = response.read(self.policy.maximum_bytes + 1)
        return body


class CompositeOpportunitySource:
    """Combine several controlled sources while preserving deterministic order."""

    def __init__(self, source_name: str, sources: Sequence[object]) -> None:
        if not source_name.strip():
            raise ValueError("source_name is required")
        if not sources:
            raise ValueError("sources is required")
        self.source_name = source_name
        self.sources = tuple(sources)

    def collect(self) -> Iterable[OpportunitySignal]:
        signals: list[OpportunitySignal] = []
        for source in self.sources:
            collect = getattr(source, "collect", None)
            if not callable(collect):
                raise TypeError("all composite sources must implement collect()")
            signals.extend(collect())
        return signals
