"""Streaming Claude client with cancellation.

    client = ClaudeClient.from_settings(api_key)
    async with client.stream(system, messages) as stream:
        async for text in stream:
            ...
            if unsafe:
                await stream.cancel()      # closes the connection, so no more tokens are billed

Provider errors are turned into `LLMError` with a generic message (the original is chained, never
shown), so keys and request details cannot leak into API responses.
"""
import anthropic

from app.config.settings import claude_max_tokens, claude_model

REQUEST_TIMEOUT_SECONDS = 25.0
DEFAULT_EFFORT = "low"


class LLMError(Exception):
    """Claude could not answer. `code` is `upstream_error` or `timeout` (see the API contract)."""

    def __init__(self, code: str, message: str = "The AI service is unavailable.") -> None:
        super().__init__(message)
        self.code = code


def _translate(error: Exception) -> LLMError:
    if isinstance(error, anthropic.APITimeoutError):  # check first: it is a kind of connection error
        return LLMError("timeout", "The AI service took too long to respond.")
    return LLMError("upstream_error")


class ClaudeStream:
    def __init__(self, manager) -> None:
        self._manager = manager
        self._stream = None
        self._closed = False
        self._cancelled = False
        self.stop_reason: str | None = None

    async def __aenter__(self) -> "ClaudeStream":
        try:
            self._stream = await self._manager.__aenter__()
        except anthropic.APIError as error:
            self._closed = True  # nothing was opened, so there is nothing to close
            raise _translate(error) from error
        return self

    async def __aexit__(self, *exc_info) -> bool:
        await self._close()
        return False

    def __aiter__(self):
        return self._iterate()

    async def cancel(self) -> None:
        self._cancelled = True
        await self._close()

    async def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._manager.__aexit__(None, None, None)

    async def _iterate(self):
        if self._cancelled or self._stream is None:
            return
        source = self._stream.text_stream
        try:
            async for text in source:
                yield text
                if self._cancelled:
                    return
            final = await self._stream.get_final_message()
            self.stop_reason = final.stop_reason
        except anthropic.APIError as error:
            raise _translate(error) from error
        finally:
            close = getattr(source, "aclose", None)
            if close is not None:
                await close()


class ClaudeClient:
    def __init__(self, sdk, model: str, max_tokens: int, effort: str = DEFAULT_EFFORT) -> None:
        self._sdk = sdk
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort

    @classmethod
    def from_settings(cls, api_key: str) -> "ClaudeClient":
        # One retry at most: the API gateway gives up after about 30 seconds in total.
        sdk = anthropic.AsyncAnthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1)
        return cls(sdk, claude_model(), claude_max_tokens())

    def stream(self, system: str, messages: list[dict]) -> ClaudeStream:
        # No temperature/top_p/top_k (rejected by current models). Thinking is left at the model
        # default; `effort` keeps it short and cheap for a short grounded answer.
        manager = self._sdk.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": self._effort},
        )
        return ClaudeStream(manager)
