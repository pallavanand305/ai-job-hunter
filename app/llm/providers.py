from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    retry_after = None
    try:
        retry_after = float(response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        pass
    snippet = response.text[:300].replace("\n", " ")
    if response.status_code == 429:
        raise ProviderError(
            f"rate limited: {snippet}",
            status_code=429,
            retryable=True,
            retry_after=retry_after,
        )
    if response.status_code >= 500:
        raise ProviderError(
            f"provider error {response.status_code}: {snippet}",
            status_code=response.status_code,
            retryable=True,
        )
    raise ProviderError(
        f"request failed {response.status_code}: {snippet}",
        status_code=response.status_code,
    )


class BaseProvider:
    name = "base"
    requires_key = True

    def __init__(
        self,
        model: str,
        *,
        api_key: str = "",
        base_url: str = "",
        timeout: int = 60,
        max_tokens: int = 1400,
    ) -> None:
        self.model = (model or "").strip()
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

    @property
    def usable(self) -> bool:
        return bool(self.model) and (bool(self.api_key) or not self.requires_key)

    def configuration_error(self) -> str:
        if not self.model:
            return "model is not configured"
        if self.requires_key and not self.api_key:
            return "API key is not configured"
        return ""

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        raise NotImplementedError


class GeminiProvider(BaseProvider):
    name = "gemini"

    def complete(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.2) -> str:
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        response = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_status(response)
        data = response.json()
        parts = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text:
            raise ProviderError("empty response from Gemini")
        return text


class OpenAICompatibleProvider(BaseProvider):
    name = "openai-compatible"

    def complete(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.2) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_status(response)
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise ProviderError(f"empty response from {self.name}")
        return content


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"


class OllamaProvider(BaseProvider):
    name = "ollama"
    requires_key = False

    def complete(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.2) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": self.max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        _raise_for_status(response)
        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise ProviderError("empty response from Ollama")
        return content


class TemplateProvider(BaseProvider):
    name = "template"
    requires_key = False

    def __init__(self) -> None:
        super().__init__("template-fallback")

    @property
    def usable(self) -> bool:
        return False

    def complete(self, system: str, prompt: str, *, json_mode: bool = False, temperature: float = 0.2) -> str:
        return ""


def build_provider(provider: str, model: str, role: str) -> BaseProvider | None:
    name = (provider or "").strip().lower()
    common = {
        "timeout": settings.llm_timeout,
        "max_tokens": settings.llm_max_tokens,
    }
    if name == "gemini":
        return GeminiProvider(model, api_key=settings.gemini_api_key, base_url=settings.gemini_base_url, **common)
    if name == "groq":
        return GroqProvider(model, api_key=settings.groq_api_key, base_url=settings.groq_base_url, **common)
    if name == "openrouter":
        return OpenRouterProvider(
            model, api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url, **common
        )
    if name == "openai":
        return OpenAIProvider(
            model, api_key=settings.openai_api_key, base_url=settings.openai_base_url, **common
        )
    if name == "ollama" and settings.llm_allow_ollama:
        return OllamaProvider(
            model, base_url=settings.ollama_base_url, **common
        )
    return None
