"""Ollama HTTP adapter.

Talks to a locally running ``ollama serve`` (default http://127.0.0.1:11434).
Uses the ``/api/chat`` endpoint with ``format: "json"`` for structured
output. If the model returns invalid JSON, we retry with a stricter
instruction; if it still fails we surface a clean error to the caller.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from models.llm.base import LLMEngine, LLMResponse

log = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaLLMEngine(LLMEngine):
    name = "ollama"

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _chat(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                r = await client.post(
                    f"{self.base_url}/api/chat", json=payload
                )
        except httpx.HTTPError as exc:
            raise OllamaError(f"cannot reach ollama at {self.base_url}: {exc}") from exc

        if r.status_code != 200:
            raise OllamaError(f"ollama HTTP {r.status_code}: {r.text[:500]}")

        body = r.json()
        text = (body.get("message") or {}).get("content", "")
        return LLMResponse(
            text=str(text),
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
        )

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self._chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
        )

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: dict,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict:
        schema_repr = json.dumps(schema, ensure_ascii=False, indent=2)
        strict_system = (
            (system or "")
            + "\n\nYou MUST reply with a single JSON object matching this schema."
            + " No prose, no markdown, no code fences.\n\nSchema:\n"
            + schema_repr
        ).strip()

        last_text = ""
        for attempt in (1, 2):
            messages = [
                {"role": "system", "content": strict_system},
                {"role": "user", "content": prompt},
            ]
            if attempt == 2:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply was not valid JSON. Reply now "
                            "with ONLY the JSON object, no extra text."
                        ),
                    }
                )
            resp = await self._chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            last_text = resp.text
            try:
                data = json.loads(last_text)
            except json.JSONDecodeError:
                log.warning("ollama returned invalid JSON on attempt %d", attempt)
                continue
            if not isinstance(data, dict):
                log.warning("ollama returned non-object JSON on attempt %d", attempt)
                continue
            return data

        raise OllamaError(f"ollama did not return valid JSON: {last_text[:500]}")
