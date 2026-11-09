"""The only module that talks to the language model and the embedding model (OpenRouter)."""
import logging

from app import config
from app.state import Turn

log = logging.getLogger("helpdesk.llm")


class LLM:
    def __init__(self) -> None:
        from openai import AsyncOpenAI    # imported here so the rest of the app can be tested without it

        if not config.OPENROUTER_API_KEY:
            log.warning("OPENROUTER_API_KEY is empty: model calls will fail")
        self._no_temperature: set[str] = set()   # models that refused temperature=0
        self.client = AsyncOpenAI(api_key=config.OPENROUTER_API_KEY or "missing",
                                  base_url=config.OPENROUTER_BASE_URL,
                                  timeout=config.LLM_TIMEOUT_S, max_retries=1)

    async def complete(self, system: str, user: str, turn: Turn | None = None,
                       json_mode: bool = False, max_tokens: int = 700, model: str | None = None) -> str:
        """One chat completion. temperature 0 so the same input gives the same output."""
        from openai import BadRequestError

        model = model or config.MODEL
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        if model not in self._no_temperature:
            kwargs["temperature"] = 0
        try:
            response = await self._create(model, system, user, max_tokens, kwargs)
        except BadRequestError as exc:
            # Some newer models only accept their default temperature. Retry once without it.
            if "temperature" not in kwargs or "temperature" not in str(exc).lower():
                raise
            log.warning("%s rejects temperature=0, retrying without it", model)
            self._no_temperature.add(model)
            kwargs.pop("temperature")
            response = await self._create(model, system, user, max_tokens, kwargs)
        if turn is not None and response.usage:
            extra = response.usage.model_extra or {}
            turn.add_usage(response.usage.prompt_tokens, response.usage.completion_tokens, extra.get("cost"))
        return response.choices[0].message.content or ""

    async def _create(self, model: str, system: str, user: str, max_tokens: int, kwargs: dict):
        return await self.client.chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body={"usage": {"include": True}},     # OpenRouter then reports the cost
            **kwargs)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]
