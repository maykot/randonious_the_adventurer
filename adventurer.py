import asyncio
import os
import re

from typing import Awaitable, Callable, Type

from assistant import Assistant, Prompt
from logger import Logger, LogLevel, LogMessage
from preprompt_loader import load_preprompts

PREPROMPTS_FOLDER = os.path.join("preprompts", "adventurer")
PREPROMPT_NAMES = ["adventurer", "attributes", "description"]
PREPROMPTS_DICT = load_preprompts(PREPROMPTS_FOLDER, PREPROMPT_NAMES)


class Preprompts:
    adventurer: str = PREPROMPTS_DICT["adventurer"]
    attributes: str = PREPROMPTS_DICT["attributes"]
    description: str = PREPROMPTS_DICT["description"]


LOG_NAME = "Adventurer"
DEFAULT_USER = "user"


class MessageTemplates:
    new_adventurer = "Creating new adventurer"
    new_preprompt = "Creating character preprompt"
    new_description = "Creating character description"
    new_attributes = "Creating character attributes"
    preprompt_created = "Preprompt created:\n{content}"
    found_messages = "Found {n} new messages. Sending them to the assistant"
    response_received = "Response received:\n{content}"
    clearing_queue = "Clearing message queue"
    chat_error = "Error while talking to the assistant"
    q_add = "Adding message to the queue:\n{author}: {content}"
    adventurer_ready = "New adventurer ready, wait for their introduction"
    intro_prompt = "Introduce yourself."


class Adventurer:
    def __init__(
        self,
        assistant: Type[Assistant],
        logger: Logger,
    ) -> None:
        self._assistant = assistant
        self._conversation = self._assistant(logger)
        self._conversation_queue: list[Prompt] = []
        self._chat_cbs: list[Callable[[str], Awaitable[None]]] = [self._log]
        self._logger = logger
        self._loop_throttle_time = 5

    async def ainit(self) -> None:
        await self._log(MessageTemplates.new_adventurer, level=LogLevel.Info)
        await self._conversation.ainit()
        self._character_preprompt = await self._build_preprompt()
        self._conversation.set_preprompt(self._character_preprompt)
        self._conversation_task = asyncio.create_task(self._conversation_loop())

    async def close(self) -> None:
        await self._conversation.close()
        self._conversation_task.cancel()

    async def refresh(self) -> None:
        await self.close()
        self._conversation_queue: list[Prompt] = []
        await self.ainit()

    def add_chat_cb(self, cb: Callable[[str], Awaitable[None]]) -> None:
        self._chat_cbs.append(cb)

    async def chat(self, author: str, content: str) -> None:
        message = MessageTemplates.q_add.format(author=author, content=content)
        await self._log(message, long_content=True)
        self._add_to_queue(author, content)

    async def intro(self) -> None:
        await self._log(MessageTemplates.adventurer_ready, level=LogLevel.Info)
        await self.chat("user", MessageTemplates.intro_prompt)

    async def _log(
        self,
        content: str,
        level: LogLevel = LogLevel.Debug,
        error: BaseException | None = None,
        long_content: bool = False,
    ) -> None:
        message = LogMessage(level, LOG_NAME, content, error, long_content)
        await self._logger.log(message)

    async def _build_preprompt(self) -> str:
        await self._log(MessageTemplates.new_preprompt)
        async with self._assistant(self._logger) as conversation:
            await self._build_description(conversation)
            await self._build_attributes(conversation)

        res = re.sub(r"\$description", self._description, Preprompts.adventurer)
        res = re.sub(r"\$attributes", self._attributes, res)
        message = MessageTemplates.preprompt_created.format(content=res)
        await self._log(message, long_content=True)
        return res

    async def _build_description(self, conversation: Assistant) -> None:
        await self._log(MessageTemplates.new_description)
        prompt = [Prompt(DEFAULT_USER, Preprompts.description)]
        self._description = await conversation.chat(prompt)

    async def _build_attributes(self, conversation: Assistant) -> None:
        await self._log(MessageTemplates.new_attributes)
        prompt = [Prompt(DEFAULT_USER, Preprompts.attributes)]
        self._attributes = await conversation.chat(prompt)

    async def _conversation_loop(self) -> None:
        await asyncio.sleep(self._loop_throttle_time)

        queue = [e for e in self._conversation_queue]
        try:
            await self._send_prompts(queue)
        except Exception as e:
            await self._log(MessageTemplates.chat_error, level=LogLevel.Error, error=e)
        finally:
            self._conversation_task = asyncio.create_task(self._conversation_loop())
            return

    async def _send_prompts(self, queue: list[Prompt]) -> None:
        if len(queue) == 0:
            return

        await self._log(MessageTemplates.found_messages.format(n=len(queue)))
        resp = await self._conversation.chat(queue)
        message = MessageTemplates.response_received.format(content=resp)

        await self._log(message, long_content=True)
        await self._log(MessageTemplates.clearing_queue)
        self._clear_queue()

        for cb in self._chat_cbs:
            await cb(resp)

    def _add_to_queue(self, author: str, content: str) -> None:
        self._conversation_queue.append(Prompt(author, content))

    def _clear_queue(self) -> None:
        self._conversation_queue = []
