"""Extensible, duplicate-safe registries for markets, adapters and networks."""
from __future__ import annotations

from threading import RLock
from typing import Generic, TypeVar

from .domain import Market

T = TypeVar("T")


class RegistryError(ValueError):
    pass


class Registry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}
        self._lock = RLock()

    def register(self, key: str, value: T, *, replace: bool = False) -> None:
        if not key or key != key.strip():
            raise RegistryError("registry key must be non-empty and normalized")
        with self._lock:
            if key in self._items and not replace:
                raise RegistryError(f"duplicate registry key: {key}")
            self._items[key] = value

    def get(self, key: str) -> T:
        with self._lock:
            try:
                return self._items[key]
            except KeyError as exc:
                raise RegistryError(f"unknown registry key: {key}") from exc

    def unregister(self, key: str) -> T:
        with self._lock:
            try:
                return self._items.pop(key)
            except KeyError as exc:
                raise RegistryError(f"unknown registry key: {key}") from exc

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._items))


class MarketRegistry(Registry[Market]):
    pass


class AdapterRegistry(Registry[object]):
    pass


class NetworkRegistry(Registry[object]):
    pass
