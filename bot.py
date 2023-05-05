from discord import Intents, Message, TextChannel
from discord.ext import commands

from adventurer import Adventurer
from logger import Logger, LogLevel, LogMessage

COMMAND_PREFIX = "/"
LOG_NAME = "Bot"


class MessageTemplates:
    online = "Online"
    bot_greet = (
        f"Chat to the adventurer once they are ready. "
        f"Use the '{COMMAND_PREFIX}refresh' command to create a new adventurer"
    )
    command = "User issued command: '{content}'"
    message = "User issued message: '{content}'"
    command_failed = "Failed to execute the following command: '{content}'"
    default_log = "**[{level}]** ({sender}) {content}"
    info_log = (
        f"**[{LogLevel.Info.name}]** ({LOG_NAME}) It seems like something went wrong."
        f"Wait a few seconds and try again. Use the command "
        f"'{COMMAND_PREFIX}refresh' if the error persists"
    )


class Bot(commands.Bot):
    def __init__(self, channel_id: int, adventurer: Adventurer, logger: Logger) -> None:
        self._channel_id = channel_id
        self._adventurer = adventurer
        self._logger = logger

        self._adventurer.add_chat_cb(self._chat_cb)
        self._logger.subscribe(self._discord_logger, LogLevel.Error)
        self._logger.subscribe(self._discord_logger, LogLevel.Info)
        intents = Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)

    async def on_ready(self) -> None:
        self._add_commands()
        self._set_channel()
        await self._log(MessageTemplates.online, level=LogLevel.Info)
        await self._log(MessageTemplates.bot_greet, level=LogLevel.Info)
        await self._adventurer.ainit()
        await self._adventurer.intro()

    async def on_message(self, message: Message) -> None:
        if self._should_be_ignored(message):
            return
        if self._is_command(message):
            await self._log(MessageTemplates.command.format(content=message.content))
            await self._process_commands(message)
            return

        await self._log(MessageTemplates.message.format(content=message.content))
        await self._process_messages(message)

    def _add_commands(self) -> None:
        @self.command()
        async def refresh(ctx) -> None:
            if ctx.message.channel.id != self._channel_id:
                return
            await self._refresh()

    def _set_channel(self) -> None:
        self._channel = self.get_channel(self._channel_id)

    def _should_be_ignored(self, message: Message) -> bool:
        return (message.author == self.user) or (message.channel != self._channel)

    def _is_command(self, message: Message) -> bool:
        return message.content.startswith(COMMAND_PREFIX)

    async def _refresh(self) -> None:
        await self._adventurer.refresh()
        await self._adventurer.intro()

    async def _chat_cb(self, content: str) -> None:
        await self._send_message(content)

    async def _process_commands(self, message: Message) -> None:
        try:
            await self.process_commands(message)
        except Exception as e:
            content = MessageTemplates.command_failed.format(content=message.content)
            await self._log(content, level=LogLevel.Error, error=e)

    async def _process_messages(self, message: Message) -> None:
        await self._adventurer.chat(message.author.name, message.content)

    async def _send_message(self, content: str) -> None:
        if isinstance(self._channel, TextChannel):
            await self._channel.send(content)

    async def _log(
        self,
        content: str,
        level: LogLevel = LogLevel.Debug,
        error: BaseException | None = None,
        long_content: bool = False,
    ) -> None:
        message = LogMessage(level, LOG_NAME, content, error, long_content)
        await self._logger.log(message)

    async def _discord_logger(self, message: LogMessage) -> None:
        content = MessageTemplates.default_log.format(
            level=message.level.name,
            sender=message.sender,
            content=message.content,
        )
        await self._send_message(content)
        if message.level == LogLevel.Error:
            content = MessageTemplates.info_log
            await self._send_message(content)
