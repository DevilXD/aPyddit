from __future__ import annotations

from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from .utils import JsonType
    from .client import HTTPClient


class ClientBase:
    def __init__(self, client: HTTPClient):
        self._client = client


class Thing(ClientBase):
    def __init__(self, client: HTTPClient, thing_data: JsonType):
        super().__init__(client)
        self.kind: str = thing_data["kind"]
        self.id: str = thing_data["data"]["id"]
        self.name: str = thing_data["data"]["name"]
        assert not self.id.startswith(self.kind)

    @property
    def fullname(self) -> str:
        return f"{self.kind}_{self.id}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: ({self.name})"

    def __eq__(self, other):
        return self.fullname == other.fullname


class PartialThing(ClientBase, ABC):
    def __init__(self, client: HTTPClient, kind: str):
        super().__init__(client)
        self.kind: str = kind

    def __await__(self):
        return self._upgrade().__await__()

    @abstractmethod
    def _upgrade(self):
        raise NotImplementedError


class PartialNameThing(PartialThing):
    def __init__(self, client: HTTPClient, kind: str, display_name: str):
        super().__init__(client, kind)
        self.display_name: str = display_name


class PartialIDThing(PartialThing):
    def __init__(self, client: HTTPClient, kind: str, thing_id: str):
        super().__init__(client, kind)
        self.id = thing_id

    @property
    def fullname(self) -> str:
        return f"{self.kind}_{self.id}"
