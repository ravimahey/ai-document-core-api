from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
import openai

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMGenerationResult:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class BaseLLMService(ABC):
    @abstractmethod
    def generate_chat_response(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
    ) -> LLMGenerationResult:
        """Generate an AI chat response given conversation message history."""
        pass


class OpenAILLMService(BaseLLMService):
    def __init__(self, settings: Settings):
        self._settings = settings

    def _get_chat_model(self) -> ChatOpenAI:
        if not self._settings.openai_api_key:
            raise LLMAuthenticationError(
                "OpenAI API key is not configured on the server. Please set OPENAI_API_KEY."
            )

        return ChatOpenAI(
            model=self._settings.openai_model,
            api_key=self._settings.openai_api_key,
            temperature=self._settings.openai_temperature,
            max_tokens=self._settings.openai_max_output_tokens,
            timeout=self._settings.chat_request_timeout_seconds,
            max_retries=1,
        )

    def generate_chat_response(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
    ) -> LLMGenerationResult:
        sys_prompt = system_prompt or self._settings.chat_system_prompt
        prompt_messages: list[BaseMessage] = [SystemMessage(content=sys_prompt)]
        prompt_messages.extend(messages)

        model = self._get_chat_model()

        try:
            response = model.invoke(prompt_messages)
        except openai.AuthenticationError as exc:
            logger.error("OpenAI authentication error: %s", exc)
            raise LLMAuthenticationError(
                "Invalid OpenAI credentials or API key."
            ) from exc
        except (openai.APITimeoutError, TimeoutError) as exc:
            logger.error("OpenAI timeout error: %s", exc)
            raise LLMTimeoutError(
                "OpenAI request timed out. Please try again."
            ) from exc
        except (openai.RateLimitError, openai.APIConnectionError) as exc:
            logger.error("OpenAI provider connectivity/rate error: %s", exc)
            raise LLMProviderError(
                "OpenAI service rate limited or temporarily unreachable."
            ) from exc
        except Exception as exc:
            logger.error("Unexpected error invoking OpenAI model: %s", exc)
            raise LLMProviderError(
                "Failed to generate response from AI provider."
            ) from exc

        # Extract content
        content_text = str(response.content)

        # Extract token usage metadata if available
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        total_tokens: int | None = None

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage: dict[str, Any] = response.usage_metadata
            prompt_tokens = usage.get("input_tokens")
            completion_tokens = usage.get("output_tokens")
            total_tokens = usage.get("total_tokens")
        elif hasattr(response, "response_metadata") and response.response_metadata:
            usage = response.response_metadata.get("token_usage", {})
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")

        return LLMGenerationResult(
            content=content_text,
            model=self._settings.openai_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


class MockLLMService(BaseLLMService):
    """Mock LLM service for testing and development without OpenAI credentials."""

    def __init__(
        self,
        preset_response: str = "This is a simulated AI assistant response.",
        should_fail: bool = False,
        failure_type: str = "provider",
    ):
        self.preset_response = preset_response
        self.should_fail = should_fail
        self.failure_type = failure_type
        self.invoked_messages: list[list[BaseMessage]] = []

    def generate_chat_response(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
    ) -> LLMGenerationResult:
        self.invoked_messages.append(messages)

        if self.should_fail:
            if self.failure_type == "timeout":
                raise LLMTimeoutError("Simulated LLM timeout error.")
            if self.failure_type == "auth":
                raise LLMAuthenticationError("Simulated LLM auth error.")
            raise LLMProviderError("Simulated LLM provider error.")

        return LLMGenerationResult(
            content=self.preset_response,
            model="mock-gpt-4.1-nano",
            prompt_tokens=15,
            completion_tokens=10,
            total_tokens=25,
        )


def get_llm_service(
    settings: Settings | None = None,
) -> BaseLLMService:
    settings = settings or get_settings()
    return OpenAILLMService(settings=settings)
