from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


class AIProviderError(Exception):
    def __init__(self, category: str, *, retryable: bool = False) -> None:
        super().__init__(category)
        self.category = category
        self.retryable = retryable


class AIProviderNotConfigured(AIProviderError):
    def __init__(self) -> None:
        super().__init__("provider_not_configured")


class AIInputTooLarge(AIProviderError):
    def __init__(self) -> None:
        super().__init__("input_too_large")


@dataclass(frozen=True)
class GeneratedText:
    text: str
    input_tokens: int | None
    output_tokens: int | None


class TextProvider(Protocol):
    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        instructions: str,
        prompt: str,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> GeneratedText: ...


class OpenAITextProvider:
    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        instructions: str,
        prompt: str,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> GeneratedText:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        try:
            response = await client.responses.create(
                model=model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=max_output_tokens,
                store=False,
            )
        except Exception as exc:
            raise _provider_error(exc) from exc
        finally:
            await client.close()
        usage = response.usage
        result = GeneratedText(
            text=(response.output_text or "").strip(),
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )
        if not result.text:
            raise AIProviderError("empty_provider_response")
        return result


class GeminiTextProvider:
    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        instructions: str,
        prompt: str,
        max_output_tokens: int,
        timeout_seconds: float,
    ) -> GeneratedText:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        async_client = client.aio
        try:
            response = await asyncio.wait_for(
                async_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=instructions,
                        max_output_tokens=max_output_tokens,
                    ),
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise AIProviderError("provider_timeout", retryable=True) from exc
        except Exception as exc:
            raise _provider_error(exc) from exc
        finally:
            await async_client.aclose()
        usage = response.usage_metadata
        result = GeneratedText(
            text=(response.text or "").strip(),
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
        )
        if not result.text:
            raise AIProviderError("empty_provider_response")
        return result


def _provider_error(error: Exception) -> AIProviderError:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "code", None)
    if status_code == 429:
        category, retryable = "provider_rate_limited", True
    elif status_code in {408, 409} or (isinstance(status_code, int) and status_code >= 500):
        category, retryable = "provider_temporarily_unavailable", True
    elif isinstance(error, (TimeoutError, asyncio.TimeoutError)) or any(
        "timeout" in error_type.__name__.lower() for error_type in type(error).__mro__
    ):
        category, retryable = "provider_timeout", True
    elif any(
        error_type.__name__ in {"APIConnectionError", "ConnectError", "NetworkError"}
        for error_type in type(error).__mro__
    ):
        category, retryable = "provider_temporarily_unavailable", True
    else:
        category, retryable = "provider_request_failed", False
    logger.warning("ai_provider_request_failed", extra={"category": category})
    return AIProviderError(category, retryable=retryable)


def provider_key(settings: Settings, provider: str) -> str:
    configured = settings.openai_api_key if provider == "openai" else settings.gemini_api_key
    if configured is None:
        raise AIProviderNotConfigured()
    return configured.get_secret_value()


def configured_model(settings: Settings, provider: str) -> str:
    return settings.ai_openai_model if provider == "openai" else settings.ai_gemini_model


def make_provider(provider: str) -> TextProvider:
    if provider == "openai":
        return OpenAITextProvider()
    if provider == "gemini":
        return GeminiTextProvider()
    raise AIProviderError("unsupported_provider")


async def generate_text(
    settings: Settings,
    *,
    provider: str,
    model: str,
    instructions: str,
    prompt: str,
) -> GeneratedText:
    if len(prompt) + len(instructions) > settings.ai_max_input_characters:
        raise AIInputTooLarge()
    if model != configured_model(settings, provider):
        raise AIProviderError("provider_model_not_allowed")
    key = provider_key(settings, provider)
    text_provider = make_provider(provider)
    last_error: AIProviderError | None = None
    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                text_provider.generate(
                    api_key=key,
                    model=model,
                    instructions=instructions,
                    prompt=prompt,
                    max_output_tokens=settings.ai_max_output_tokens,
                    timeout_seconds=settings.ai_request_timeout_seconds,
                ),
                timeout=settings.ai_request_timeout_seconds,
            )
        except TimeoutError as exc:
            last_error = AIProviderError("provider_timeout", retryable=True)
            last_error.__cause__ = exc
        except AIProviderError as exc:
            last_error = exc
        if attempt == 1 or not last_error.retryable:
            break
        await asyncio.sleep(0.25)
    assert last_error is not None
    raise last_error
