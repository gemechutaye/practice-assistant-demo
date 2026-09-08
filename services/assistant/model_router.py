"""One hosted gateway, explicit model routes, and measured request outcomes."""

import base64
from dataclasses import dataclass
import time

import httpx
from opentelemetry import trace

from .config import Settings
from .public_content import parse_model_json

tracer = trace.get_tracer("practice_assistant.models")


class ModelError(Exception):
    def __init__(self, message: str, code: str = "model_unavailable"):
        super().__init__(message)
        self.code = code


@dataclass
class Completion:
    message: dict
    model: str
    provider: str | None
    usage: dict
    duration_ms: int
    request_id: str | None = None


class Models:
    def __init__(self, config: Settings):
        from .telemetry import configure

        configure()
        self.config = config
        self.client = httpx.Client(
            base_url="https://openrouter.ai/api/v1/",
            headers={
                "Authorization": f"Bearer {config.openrouter_key}",
                "X-Title": "Practice Assistant - independent demonstration",
            },
            timeout=httpx.Timeout(75, connect=15),
        )

    def _post(self, path: str, body: dict) -> dict:
        for attempt in range(2):
            try:
                response = self.client.post(path, json=body)
            except httpx.RequestError:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                raise ModelError("The model service could not be reached. Please retry.") from None
            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                time.sleep(0.7)
                continue
            if response.is_error:
                raise ModelError(f"The model service returned HTTP {response.status_code}.")
            data = response.json()
            if data.get("error"):
                raise ModelError("The model service did not complete this request.")
            return data
        raise ModelError("The model request did not complete.")

    def complete(
        self,
        messages: list,
        tools: list | None,
        model: str,
        max_tokens: int = 2400,
        response_format: dict | None = None,
    ) -> Completion:
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
        if tools:
            body.update(tools=tools, parallel_tool_calls=False)
        if response_format:
            body["response_format"] = response_format
        started = time.monotonic()
        with tracer.start_as_current_span("model.complete") as span:
            span.set_attribute("gen_ai.request.model", model)
            data = self._post("chat/completions", body)
            choices = data.get("choices") or []
            if not choices or not isinstance(choices[0].get("message"), dict):
                raise ModelError("The model returned no usable response.", "invalid_model_response")
            message = choices[0]["message"]
            # Persist the public answer/tool calls, never provider hidden reasoning fields.
            clean = {"role": "assistant", "content": message.get("content")}
            if message.get("tool_calls"):
                clean["tool_calls"] = message["tool_calls"]
            usage = data.get("usage") or {}
            span.set_attribute("gen_ai.response.model", data.get("model", model))
            span.set_attribute("gen_ai.usage.total_tokens", int(usage.get("total_tokens", 0)))
            return Completion(
                clean,
                data.get("model", model),
                data.get("provider"),
                usage,
                round((time.monotonic() - started) * 1000),
                data.get("id"),
            )

    def classify(self, message: str) -> tuple[str, Completion]:
        completion = self.complete(
            [
                {
                    "role": "system",
                    "content": "Classify the user's office-assistant request. Return JSON with route: content if ONLY public marketing drafting/review; report if ONLY reporting/counts; otherwise planner. A mixed request is planner. Do not answer the request.",
                },
                {"role": "user", "content": message},
            ],
            None,
            self.config.fast_model,
            80,
            {"type": "json_object"},
        )
        try:
            route = parse_model_json(completion.message["content"])["route"]
        except (ValueError, KeyError, TypeError):
            route = "planner"
        return (route if route in {"content", "report", "planner"} else "planner"), completion

    def embed(self, texts: list[str]) -> tuple[list[list[float]], dict]:
        result = self._post(
            "embeddings", {"model": self.config.embedding_model, "input": texts, "dimensions": 1536}
        )
        data = sorted(result.get("data", []), key=lambda row: row["index"])
        vectors = [row["embedding"] for row in data]
        if len(vectors) != len(texts) or any(len(v) != 1536 for v in vectors):
            raise ModelError("The embedding response had unexpected dimensions.", "invalid_embedding")
        return vectors, result.get("usage", {})

    def transcribe(self, audio: bytes, audio_format: str = "wav") -> tuple[str, dict]:
        with tracer.start_as_current_span("model.transcribe") as span:
            span.set_attribute("gen_ai.request.model", self.config.transcription_model)
            result = self._post(
                "audio/transcriptions",
                {
                    "model": self.config.transcription_model,
                    "input_audio": {"data": base64.b64encode(audio).decode(), "format": audio_format},
                },
            )
            text = result.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ModelError("No speech was recognized. Please try again.")
            return text.strip(), result.get("usage", {})

    def _post_audio(self, body: dict) -> tuple[bytes, dict]:
        for attempt in range(2):
            try:
                response = self.client.post("audio/speech", json=body)
            except httpx.RequestError:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                raise ModelError("The speech service could not be reached. Please retry.") from None
            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                time.sleep(0.7)
                continue
            if response.is_error:
                raise ModelError(f"The speech service returned HTTP {response.status_code}.")
            media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if media_type not in {"audio/mpeg", "audio/mp3", "audio/x-mp3"} or not response.content:
                raise ModelError("The speech model returned no playable audio.", "invalid_audio_response")
            # This endpoint returns audio bytes, not token usage or a confirmed charge.
            return response.content, {"request_id": response.headers.get("x-generation-id")}
        raise ModelError("The speech request did not complete.")

    def speak(self, text: str) -> tuple[bytes, dict]:
        with tracer.start_as_current_span("model.speak") as span:
            span.set_attribute("gen_ai.request.model", self.config.speech_model)
            audio, usage = self._post_audio(
                {
                    "model": self.config.speech_model,
                    "input": text,
                    "voice": self.config.speech_voice,
                    "response_format": "mp3",
                }
            )
            return audio, {**usage, "input_characters": len(text)}
