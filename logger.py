from datetime import datetime
from enum import auto, Enum
from typing import Awaitable, Callable, NamedTuple

LONG_CONTENT_SEP = "\n|------------------------|\n"


class LogLevel(Enum):
    Info = auto()
    Debug = auto()
    Error = auto()
    All = auto()


class LogMessage(NamedTuple):
    level: LogLevel
    sender: str
    content: str
    error: BaseException | None = None
    long_content: bool = False


class Logger:
    def __init__(self) -> None:
        self.subscribers = {level: set() for level in LogLevel}
        self.subscribe(self.console_logger, LogLevel.All)

    @staticmethod
    async def console_logger(message: LogMessage) -> None:
        print(Logger.build_log_content(message))

    def subscribe(
        self, cb: Callable[[LogMessage], Awaitable[None]], level: LogLevel
    ) -> None:
        self.subscribers[level].add(cb)

    async def log(self, message: LogMessage) -> None:
        for cb in self.subscribers[message.level].union(self.subscribers[LogLevel.All]):
            await cb(message)

    @staticmethod
    def build_log_content(
        message: LogMessage,
        timestamp: bool = True,
        level: bool = True,
        sender: bool = True,
        content: bool = True,
        error: bool = True,
        long_content_sep: str = LONG_CONTENT_SEP,
    ) -> str:
        log = []
        if timestamp:
            log.append(datetime.now().isoformat())
        if level:
            log.append(f"[{message.level.name}]")
        if sender:
            log.append(f"({message.sender})")
        if content:
            body = f"{message.content}"
            if message.long_content:
                body = long_content_sep + body + long_content_sep
            log.append(body)

        log_error = ""
        if error and message.error is not None:
            log_error = f"\n\t{type(message.error).__name__}: " + str(message.error)

        return " ".join(log) + log_error
