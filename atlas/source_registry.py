from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from atlas.real_world_sources import HttpJsonOpportunitySource, HttpSourcePolicy


@dataclass(frozen=True)
class SourceRegistryEntry:
    name: str
    endpoint_url: str
    allowed_hosts: tuple[str, ...]
    timeout_seconds: float = 10.0
    maximum_bytes: int = 1_000_000
    enabled: bool = True

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("source name is required")
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("source endpoint_url must be absolute HTTPS")
        if parsed.hostname not in self.allowed_hosts:
            raise ValueError("source endpoint host must be allowlisted")
        HttpSourcePolicy(
            allowed_hosts=self.allowed_hosts,
            timeout_seconds=self.timeout_seconds,
            maximum_bytes=self.maximum_bytes,
        ).validate()


class OpportunitySourceRegistry:
    """Load controlled HTTP opportunity sources from versioned JSON configuration."""

    def __init__(self, entries: Iterable[SourceRegistryEntry]) -> None:
        self.entries = tuple(entries)
        names = [entry.name for entry in self.entries]
        if len(names) != len(set(names)):
            raise ValueError("source names must be unique")
        for entry in self.entries:
            entry.validate()

    @classmethod
    def from_file(cls, path: str | Path) -> "OpportunitySourceRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise ValueError("source registry schema_version must be 1.0")
        raw_sources = payload.get("sources")
        if not isinstance(raw_sources, list):
            raise ValueError("source registry must contain a sources list")
        entries: list[SourceRegistryEntry] = []
        for index, item in enumerate(raw_sources):
            if not isinstance(item, dict):
                raise ValueError(f"source registry item {index} must be an object")
            entries.append(cls._entry_from_dict(item, index))
        return cls(entries)

    @staticmethod
    def _entry_from_dict(item: dict[str, Any], index: int) -> SourceRegistryEntry:
        allowed_hosts = item.get("allowed_hosts")
        if not isinstance(allowed_hosts, list) or not all(isinstance(host, str) for host in allowed_hosts):
            raise ValueError(f"source registry item {index} allowed_hosts must be a string list")
        return SourceRegistryEntry(
            name=str(item.get("name") or ""),
            endpoint_url=str(item.get("endpoint_url") or ""),
            allowed_hosts=tuple(allowed_hosts),
            timeout_seconds=float(item.get("timeout_seconds", 10.0)),
            maximum_bytes=int(item.get("maximum_bytes", 1_000_000)),
            enabled=bool(item.get("enabled", True)),
        )

    def build_sources(self) -> list[HttpJsonOpportunitySource]:
        return [
            HttpJsonOpportunitySource(
                source_name=entry.name,
                endpoint_url=entry.endpoint_url,
                policy=HttpSourcePolicy(
                    allowed_hosts=entry.allowed_hosts,
                    timeout_seconds=entry.timeout_seconds,
                    maximum_bytes=entry.maximum_bytes,
                ),
            )
            for entry in self.entries
            if entry.enabled
        ]
