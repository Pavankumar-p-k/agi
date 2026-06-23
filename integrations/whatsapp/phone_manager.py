from __future__ import annotations

import logging
import os
from typing import Any

from .base import BaseWhatsAppProvider
from .models import SendResult

logger = logging.getLogger(__name__)


class WhatsAppPhoneManager:
    def __init__(self):
        self._phones: dict[str, BaseWhatsAppProvider] = {}
        self._default_phone: str | None = None

    @property
    def phone_numbers(self) -> list[str]:
        return list(self._phones.keys())

    @property
    def default_phone(self) -> str | None:
        return self._default_phone

    @default_phone.setter
    def default_phone(self, phone: str | None):
        if phone is not None and phone not in self._phones:
            raise ValueError(f"Phone {phone} not registered")
        self._default_phone = phone

    def register_phone(self, phone_number: str, provider: BaseWhatsAppProvider, make_default: bool = False):
        self._phones[phone_number] = provider
        if make_default or self._default_phone is None:
            self._default_phone = phone_number
        logger.info("[PhoneManager] Registered %s (default=%s)", phone_number, self._default_phone == phone_number)

    def unregister_phone(self, phone_number: str) -> bool:
        if phone_number not in self._phones:
            return False
        del self._phones[phone_number]
        if self._default_phone == phone_number:
            self._default_phone = next(iter(self._phones)) if self._phones else None
        return True

    def get_provider(self, phone_number: str | None = None) -> BaseWhatsAppProvider | None:
        if phone_number and phone_number in self._phones:
            return self._phones[phone_number]
        if self._default_phone:
            return self._phones.get(self._default_phone)
        return next(iter(self._phones.values())) if self._phones else None

    def resolve_phone_for_target(self, target: str) -> tuple[str, BaseWhatsAppProvider | None]:
        provider = self.get_provider()
        if not provider:
            return target, None
        return target, provider

    async def send_via(self, phone_number: str, send_fn, *args, **kwargs) -> SendResult:
        provider = self.get_provider(phone_number)
        if not provider:
            return SendResult(success=False, error=f"No provider for {phone_number}")
        return await send_fn(provider, *args, **kwargs)

    async def connect_all(self, **shared_kwargs) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for phone in list(self._phones.keys()):
            provider = self._phones[phone]
            ok = await provider.connect(**shared_kwargs)
            results[phone] = ok
            if not ok:
                logger.warning("[PhoneManager] Failed to connect %s", phone)
        return results

    async def disconnect_all(self) -> bool:
        for phone, provider in self._phones.items():
            try:
                await provider.disconnect()
            except Exception as e:
                logger.warning("[PhoneManager] Disconnect error for %s: %s", phone, e)
        self._phones.clear()
        self._default_phone = None
        return True

    async def health_check_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for phone, provider in self._phones.items():
            try:
                results[phone] = await provider.health_check()
            except Exception as e:
                logger.warning("[PhoneManager] Health check error for %s: %s", phone, e)
                results[phone] = False
        return results
