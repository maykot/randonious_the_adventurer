import os

from dotenv import load_dotenv

from adventurer import Adventurer
from bot import Bot
from huggingchat import HuggingChat
from logger import Logger

if os.path.isfile(".env"):
    load_dotenv()

discord_token = os.getenv("DISCORD_TOKEN")
if discord_token is None:
    discord_token = ""

channel_id = os.getenv("CHANNEL_ID")
if channel_id is None:
    channel_id = ""
channel_id = int(channel_id)


def main() -> None:
    logger = Logger()

    adventurer = Adventurer(HuggingChat, logger)

    bot = Bot(channel_id, adventurer, logger)
    bot.run(discord_token)


main()
