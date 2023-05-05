from abc import ABC, abstractmethod
from typing import NamedTuple, Self

from logger import Logger


class Prompt(NamedTuple):
    author: str
    content: str


class Assistant(ABC):
    @abstractmethod
    def __init__(self, logger: Logger) -> None:
        pass

    @abstractmethod
    async def __aenter__(self) -> Self:
        pass

    @abstractmethod
    async def __aexit__(self, *exc) -> None:
        pass

    @abstractmethod
    async def ainit(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    def set_preprompt(self, preprompt: str) -> None:
        pass

    @abstractmethod
    async def chat(self, prompt: list[Prompt]) -> str:
        pass


class DummyAssistant(Assistant):
    def __init__(self, logger: Logger) -> None:
        self._logger = logger
        self._preprompt = ""
        self._history: list[Prompt] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    async def ainit(self) -> Self:
        return await self.__aenter__()

    async def close(self) -> None:
        pass

    def set_preprompt(self, preprompt: str) -> None:
        self._preprompt = preprompt
        return

    async def chat(self, prompts: list[Prompt]) -> str:
        self._history.extend(prompts)
        res = [f"{prompt.author = }\n{prompt.content = }" for prompt in prompts]
        res = "\n\n".join(res)
        return res
