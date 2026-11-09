from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any

import httpx

from app.config import settings
from app.llm.providers import BaseProvider, ProviderError, build_provider
from app.llm.rate_limit import CallRateLimiter, RateLimitExceeded

logger = logging.getLogger(__name__)


def _strip_json(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start > 0:
        text = text[start:]
    return text


def _parse_json(text: str) -> Any:
    cleaned = _strip_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        value, _ = decoder.raw_decode(cleaned)
        return value


class LLMClient:
    """Provider-agnostic LLM wrapper: primary -> secondary -> template fallback."""

    def __init__(self) -> None:
        self.rate_limiter = CallRateLimiter()
        self.last_provider: BaseProvider | None = None
        self.last_error = ""
        self._specs = self._build_specs()
        self.chain = self._dedupe(
            [spec["provider_obj"] for spec in self._specs if spec["provider_obj"] and spec["provider_obj"].usable]
        )
        if not self.chain:
            self.last_error = self._configuration_reason()

    def _build_specs(self) -> list[dict[str, Any]]:
        primary = self._primary_choice()
        secondary = self._secondary_choice()
        specs = [
            self._spec("primary", primary[0], primary[1]),
            self._spec("secondary", secondary[0], secondary[1]),
        ]
        if settings.openrouter_api_key and settings.openrouter_model:
            specs.append(self._spec("optional", "openrouter", settings.openrouter_model))
        if settings.llm_allow_ollama and settings.ollama_model:
            specs.append(self._spec("optional", "ollama", settings.ollama_model))
        return specs

    def _primary_choice(self) -> tuple[str, str]:
        name = (settings.llm_primary_provider or "").strip().lower()
        model = settings.llm_primary_model
        legacy = (settings.llm_provider or "auto").strip().lower()
        if name in {"", "auto"}:
            if legacy in {"", "auto"}:
                if settings.openai_api_key:
                    name = "openai"
                    model = model or settings.openai_model
                elif settings.llm_allow_ollama:
                    name = "ollama"
                    model = model or settings.ollama_model
                else:
                    name = "gemini"
            elif legacy == "mock":
                return ("", "")
            else:
                name = legacy
                model = model or (
                    settings.openai_model if name == "openai" else settings.ollama_model
                )
        return (name, model)

    def _secondary_choice(self) -> tuple[str, str]:
        name = (settings.llm_secondary_provider or "").strip().lower()
        model = settings.llm_secondary_model
        return (name, model)

    def _spec(self, role: str, provider: str, model: str) -> dict[str, Any]:
        name = (provider or "").strip().lower()
        provider_obj = build_provider(name, model, role) if name else None
        error = ""
        if provider_obj is None:
            error = f"unsupported or disabled provider '{name}'" if name else "provider is not configured"
        else:
            error = provider_obj.configuration_error()
        return {
            "role": role,
            "provider": name,
            "model": model,
            "provider_obj": provider_obj,
            "error": error,
        }

    @staticmethod
    def _dedupe(providers: list[BaseProvider]) -> list[BaseProvider]:
        seen: set[tuple[str, str]] = set()
        result: list[BaseProvider] = []
        for provider in providers:
            key = (provider.name, provider.model)
            if key in seen:
                continue
            seen.add(key)
            result.append(provider)
        return result

    def _configuration_reason(self) -> str:
        errors = []
        for spec in self._specs:
            if spec["error"]:
                errors.append(f"{spec['role']} {spec['provider'] or 'none'}: {spec['error']}")
        return "; ".join(errors) or "no LLM provider configured"

    @property
    def usable(self) -> bool:
        return bool(self.chain)

    @property
    def is_mock(self) -> bool:
        return not self.usable

    @property
    def provider(self) -> str:
        active = self.last_provider or (self.chain[0] if self.chain else None)
        return active.name if active else "template"

    @property
    def model(self) -> str:
        active = self.last_provider or (self.chain[0] if self.chain else None)
        return active.model if active else "template-fallback"

    def info(self) -> dict[str, Any]:
        active = self.last_provider or (self.chain[0] if self.chain else None)
        return {
            "provider": active.name if active else "template",
            "model": active.model if active else "template-fallback",
            "usable": self.usable,
            "fallback": not self.usable,
            "reason": "" if self.usable else self._configuration_reason(),
            "chain": [
                {
                    "role": spec["role"],
                    "provider": spec["provider"],
                    "model": spec["model"],
                    "configured": bool(spec["provider_obj"] and spec["provider_obj"].usable),
                    "error": spec["error"],
                }
                for spec in self._specs
                if spec["provider"]
            ],
            "last_error": self.last_error,
            "rate_limit": self.rate_limiter.info(),
        }

    # -- calls ----------------------------------------------------------
    def _call(
        self,
        provider: BaseProvider,
        system: str,
        prompt: str,
        *,
        json_mode: bool,
        temperature: float,
    ) -> str:
        try:
            self.rate_limiter.acquire()
        except RateLimitExceeded as exc:
            self.last_error = str(exc)
            raise ProviderError(str(exc), status_code=429, retryable=False) from exc

        logger.debug(
            "LLM request provider=%s model=%s json=%s prompt=%s",
            provider.name,
            provider.model,
            json_mode,
            prompt,
        )
        attempts = max(0, int(settings.llm_max_retries))
        for attempt in range(attempts + 1):
            try:
                raw = provider.complete(
                    system,
                    prompt,
                    json_mode=json_mode,
                    temperature=temperature,
                )
                logger.debug(
                    "LLM response provider=%s model=%s response=%s",
                    provider.name,
                    provider.model,
                    raw,
                )
                self.last_error = ""
                return raw
            except ProviderError as exc:
                self.last_error = f"{provider.name}: {exc}"
                rate_limited = exc.status_code == 429
                timed_out = isinstance(exc.__cause__, httpx.TimeoutException)
                if (rate_limited or timed_out or exc.retryable) and attempt < attempts:
                    delay = exc.retry_after
                    if delay is None:
                        delay = float(settings.llm_backoff_seconds) * (2**attempt)
                    delay = min(delay, float(settings.llm_max_retry_wait_seconds))
                    logger.warning(
                        "LLM %s retrying in %.1fs after error: %s",
                        provider.name,
                        max(0.5, delay),
                        exc,
                    )
                    time.sleep(max(0.5, delay))
                    continue
                raise
            except httpx.TimeoutException as exc:
                self.last_error = f"{provider.name}: timeout: {exc}"
                if attempt < attempts:
                    time.sleep(max(0.5, float(settings.llm_backoff_seconds) * (2**attempt)))
                    continue
                raise ProviderError(f"{provider.name} timed out", status_code=504) from exc
            except Exception as exc:
                self.last_error = f"{provider.name}: {exc}"
                raise

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        if not self.chain:
            return ""
        for provider in self.chain:
            try:
                raw = self._call(
                    provider, system, prompt, json_mode=json_mode, temperature=temperature
                )
                self.last_provider = provider
                return raw
            except Exception as exc:
                logger.warning("LLM provider %s failed: %s", provider.name, exc)
        return ""

    def complete_json(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        default: Any = None,
        schema: Any = None,
    ) -> Any:
        if not self.chain:
            return default
        for provider in self.chain:
            prompt_for_attempt = prompt
            for attempt in range(2):
                try:
                    raw = self._call(
                        provider,
                        system,
                        prompt_for_attempt,
                        json_mode=True,
                        temperature=temperature,
                    )
                    data = _parse_json(raw)
                    if schema is not None:
                        data = schema.model_validate(data).model_dump()
                    self.last_provider = provider
                    return data
                except Exception as exc:
                    self.last_error = f"{provider.name}: {exc}"
                    if attempt == 0:
                        prompt_for_attempt = (
                            f"{prompt}\n\nYour previous response was invalid: {exc}. "
                            "Return ONLY valid JSON that matches the requested schema. "
                            "Do not add markdown fences or commentary."
                        )
                        continue
                    logger.warning("LLM provider %s returned invalid JSON: %s", provider.name, exc)
                    break
        return default

    def test_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for spec in self._specs:
            provider = spec["provider_obj"]
            if not spec["provider"]:
                continue
            key = (spec["provider"], spec["model"])
            if key in seen:
                continue
            seen.add(key)
            base = {
                "role": spec["role"],
                "provider": spec["provider"],
                "model": spec["model"] or "not set",
            }
            if provider is None or not provider.usable:
                results.append(
                    {
                        **base,
                        "ok": False,
                        "status": "missing_config",
                        "error": spec["error"],
                    }
                )
                continue
            try:
                raw = self._call(
                    provider,
                    "You are a health check. Return JSON only.",
                    'Return exactly: {"ok": true}',
                    json_mode=True,
                    temperature=0.0,
                )
                data = _parse_json(raw)
                if isinstance(data, dict) and data.get("ok") is True:
                    results.append({**base, "ok": True, "status": "ok", "error": ""})
                else:
                    results.append(
                        {
                            **base,
                            "ok": False,
                            "status": "invalid_response",
                            "error": f"unexpected JSON: {str(data)[:200]}",
                        }
                    )
            except Exception as exc:
                results.append(
                    {
                        **base,
                        "ok": False,
                        "status": "error",
                        "error": str(exc)[:500],
                    }
                )
        return results


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()
