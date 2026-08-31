from __future__ import annotations

import asyncio
import logging

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError

logger = logging.getLogger(__name__)

# Связь с Telegram с этого сервера временами обрывается по таймауту (замечено
# и на IPv4, и на IPv6 - похоже на нестабильную маршрутизацию, а не блокировку
# конкретного протокола). Вместо одной попытки на 60 секунд - несколько
# попыток покороче с паузой между ними.
REQUEST_TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


class ResilientAiohttpSession(AiohttpSession):
    """AiohttpSession с автоповтором при сетевых сбоях (TelegramNetworkError)."""

    async def make_request(self, bot, method, timeout: int | None = None):
        request_timeout = timeout if timeout is not None else REQUEST_TIMEOUT_SECONDS
        last_error: TelegramNetworkError | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await super().make_request(bot, method, timeout=request_timeout)
            except TelegramNetworkError as error:
                last_error = error
                if attempt < MAX_ATTEMPTS:
                    logger.warning(
                        "Сетевой сбой при обращении к Telegram (попытка %s/%s): %s. Повтор через %sс.",
                        attempt,
                        MAX_ATTEMPTS,
                        error,
                        RETRY_DELAY_SECONDS,
                    )
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        assert last_error is not None
        raise last_error
