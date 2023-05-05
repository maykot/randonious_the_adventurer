import asyncio
import json
import os
import re
import uuid

from datetime import datetime, timedelta
from requests import Response, Session
from typing import Self

from assistant import Assistant, Prompt
from logger import Logger, LogLevel, LogMessage
from preprompt_loader import load_preprompts

DOMAIN = "https://huggingface.co"
USER_MESSAGE_TOKEN = "<|user|>"
ASSISTANT_MESSAGE_TOKEN = "<|assistant|>"
SEP_TOKEN = "</s>"
PREPROMPT_SEP = "\n-----\n"

PREPROMPTS_FOLDER = os.path.join("preprompts", "huggingchat")
PREPROMPT_NAMES = ["default"]
PREPROMPTS_DICT = load_preprompts(PREPROMPTS_FOLDER, PREPROMPT_NAMES)

LOG_NAME = "HuggingChat"


class Preprompts:
    default: str = PREPROMPTS_DICT["default"]


class MessageTemplates:
    post_failed = "Failed to post request to HuggingChat"
    conn_failed = "Failed to establish connection to HuggingChat"
    new_chat_failed = "Failed to create new chat ({i}/{n})"


class Parameters:
    max_new_tokens: int = 1024
    repetition_penalty: float = 1.2
    return_full_text: int = False
    stop: list[str] = [SEP_TOKEN]
    temperature: float = 0.9
    top_k: int = 50
    top_p: float = 0.95
    truncate: int = 1024
    watermark: bool = False
    stream: bool = True

    @classmethod
    def dict(cls) -> dict:
        return {key: vars(cls)[key] for key in cls.__annotations__}


class Options:
    is_retry: bool = False
    use_cache: bool = False

    @classmethod
    def dict(cls) -> dict:
        return {key: vars(cls)[key] for key in cls.__annotations__}


class HuggingChat(Assistant):
    def __init__(self, logger: Logger) -> None:
        self._logger = logger

        self._base_url = f"{DOMAIN}/chat"
        self._api_route = f"{self._base_url}/conversation"

        self._throttle_time = timedelta(milliseconds=500)
        self._time_of_last_prompt = datetime.now()

    async def __aenter__(self) -> Self:
        self._clear_prompts()
        await self._set_session()
        await self._new_chat()
        return self

    async def __aexit__(self, *exc) -> None:
        self._session.close()

    async def ainit(self) -> None:
        await self.__aenter__()

    async def close(self) -> None:
        return await self.__aexit__()

    def set_preprompt(self, preprompt: str) -> None:
        self._preprompt = preprompt

    async def chat(self, prompts: list[Prompt]) -> str:
        self._update_history(prompts)
        prompt_content = self._build_prompt()
        resp = ""
        try:
            resp = await self._request_response(prompt_content)
        except Exception as e:
            message = MessageTemplates.post_failed
            await self._log(message, level=LogLevel.Error, error=e)
        else:
            self._update_history([Prompt("assistant", resp)])
        finally:
            await self._throttle()
            return resp

    def _clear_prompts(self) -> None:
        self._raw_history: list[Prompt] = []
        self._chat_history: list[str] = []
        self._split_history: list[str] = []
        self._preprompt = Preprompts.default

    async def _set_session(self) -> None:
        self._session = Session()
        try:
            self._session.get(self._base_url)
        except Exception as e:
            message = MessageTemplates.conn_failed
            await self._log(message, level=LogLevel.Error, error=e)
            raise e

    async def _log(
        self,
        content: str,
        level: LogLevel = LogLevel.Debug,
        error: BaseException | None = None,
        long_content: bool = False,
    ) -> None:
        message = LogMessage(level, LOG_NAME, content, error, long_content)
        await self._logger.log(message)

    async def _throttle(self) -> None:
        dt = datetime.now() - self._time_of_last_prompt
        if dt < self._throttle_time:
            await asyncio.sleep((self._throttle_time - dt).total_seconds())
        self._time_of_last_prompt = datetime.now()

    async def _new_chat(self) -> None:
        tries = 3
        for i in range(tries):
            try:
                resp = self._session.post(
                    self._api_route,
                    json={"model": "OpenAssistant/oasst-sft-6-llama-30b-xor"},
                    headers={"Content-Type": "application/json"},
                )
                self._chat_id = json.loads(resp.text)["conversationId"]
                self._chat_url = f"{self._api_route}/{self._chat_id}"
            except Exception as e:
                message = MessageTemplates.new_chat_failed.format(i=i + 1, n=tries)
                await self._log(message, level=LogLevel.Error, error=e)
            finally:
                await self._throttle()
                return

    def _update_history(self, prompts: list[Prompt]) -> None:
        self._raw_history.extend(prompts)
        self._chat_history = self._format_prompts(prompts)
        new_splits = [e.split(" ") for e in self._chat_history]
        self._split_history.extend(*new_splits)

    @staticmethod
    def _format_prompts(prompts: list[Prompt]) -> list[str]:
        res = []
        for prompt in prompts:
            token = (
                ASSISTANT_MESSAGE_TOKEN
                if prompt.author == "assistant"
                else USER_MESSAGE_TOKEN
            )
            res.append(f"{token}{prompt.content}{SEP_TOKEN}")
        return res

    def _build_prompt(self) -> str:
        preprompt = self._preprompt + PREPROMPT_SEP
        prompt_body = " ".join(self._split_history[-Parameters.max_new_tokens :])
        prompt_body += ASSISTANT_MESSAGE_TOKEN
        return preprompt + prompt_body

    async def _request_response(self, prompt_content: str) -> str:
        request_json = self._build_request_json(prompt_content)
        headers = self._build_headers()
        resp = self._session.post(
            self._chat_url,
            json=request_json,
            stream=Parameters.stream,
            headers=headers,
            cookies=self._session.cookies,
        )
        return await self._parse_response(resp)

    def _build_request_json(self, prompt_content: str) -> dict:
        return {
            "inputs": prompt_content,
            "parameters": Parameters.dict(),
            "options": {"id": str(uuid.uuid4()), **Options.dict()},
        }

    def _build_headers(self) -> dict:
        return {
            "Origin": DOMAIN,
            "Referer": self._chat_url,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    async def _parse_response(self, resp: Response) -> str:
        if resp.status_code != 200:
            message = (
                MessageTemplates.post_failed + f". Status code: {resp.status_code}"
            )
            await self._log(message, level=LogLevel.Error)

        out = ""
        for line in resp.iter_lines():
            resp_line = line.decode("utf-8")
            obj = json.loads(resp_line[1:-1])
            if "generated_text" in obj:
                out += obj["generated_text"]
            elif "error" in obj:
                raise Exception(obj["error"])

        # out = re.sub(r"<.*>", "", out)
        return out
