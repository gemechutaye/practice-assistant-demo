import base64
import json

import httpx
import pytest

from services.assistant.config import Settings, settings
from services.assistant.model_router import ModelError, Models


@pytest.fixture
def models():
    instance = Models(Settings(database_url="", openrouter_key="test", supabase_url="", supabase_anon_key=""))
    yield instance
    instance.client.close()


def use_transport(models, handler):
    models.client.close()
    models.client = httpx.Client(
        base_url="https://openrouter.ai/api/v1/", transport=httpx.MockTransport(handler)
    )


def test_transcription_uses_dedicated_audio_endpoint_and_preserves_provider_usage(models):
    def handler(request):
        assert request.url.path == "/api/v1/audio/transcriptions"
        payload = json.loads(request.content)
        assert payload == {
            "model": "openai/whisper-large-v3-turbo",
            "input_audio": {"data": base64.b64encode(b"synthetic wav").decode(), "format": "wav"},
        }
        return httpx.Response(
            200, json={"text": "  Prepare tomorrow. ", "usage": {"seconds": 2, "cost": 0.00001}}
        )

    use_transport(models, handler)
    assert models.transcribe(b"synthetic wav") == ("Prepare tomorrow.", {"seconds": 2, "cost": 0.00001})


@pytest.mark.parametrize("result", [{}, {"text": " "}, {"text": ["wrong type"]}])
def test_transcription_rejects_empty_or_invalid_text(models, result):
    use_transport(models, lambda request: httpx.Response(200, json=result))
    with pytest.raises(ModelError, match="No speech was recognized"):
        models.transcribe(b"synthetic wav")


def test_speech_returns_raw_mp3_bytes_with_explicit_voice_and_no_invented_cost(models):
    def handler(request):
        assert request.url.path == "/api/v1/audio/speech"
        assert json.loads(request.content) == {
            "model": "hexgrad/kokoro-82m",
            "input": "The calendar is ready.",
            "voice": "af_heart",
            "response_format": "mp3",
        }
        return httpx.Response(
            200,
            content=b"ID3 synthetic audio",
            headers={"content-type": "audio/mpeg", "x-generation-id": "test-generation"},
        )

    use_transport(models, handler)
    audio, usage = models.speak("The calendar is ready.")
    assert audio == b"ID3 synthetic audio"
    assert usage == {"request_id": "test-generation", "input_characters": 22}
    assert "cost" not in usage


@pytest.mark.parametrize(
    "headers,body",
    [
        ({"content-type": "application/json"}, b'{"error":"failed"}'),
        ({"content-type": "audio/mpeg"}, b""),
        ({}, b"not audio"),
    ],
)
def test_speech_rejects_non_audio_or_empty_success_response(models, headers, body):
    use_transport(models, lambda request: httpx.Response(200, content=body, headers=headers))
    with pytest.raises(ModelError) as error:
        models.speak("A synthetic message")
    assert error.value.code == "invalid_audio_response"


def test_speech_retries_transient_error_once(models, monkeypatch):
    monkeypatch.setattr("services.assistant.model_router.time.sleep", lambda _: None)
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, content=b"ID3 audio", headers={"content-type": "audio/mpeg"})

    use_transport(models, handler)
    assert models.speak("A synthetic message")[0] == b"ID3 audio"
    assert len(requests) == 2


def test_speech_preserves_account_rejection_without_exposing_provider_payload(models):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(403, json={"error": {"message": "secret-sensitive-provider-detail"}})

    use_transport(models, handler)
    with pytest.raises(ModelError, match="HTTP 403") as error:
        models.speak("A synthetic message")
    assert "secret" not in str(error.value)
    assert len(requests) == 1


def test_audio_routes_are_independently_configurable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("TRANSCRIPTION_MODEL", "provider/transcription")
    monkeypatch.setenv("SPEECH_MODEL", "provider/speech")
    monkeypatch.setenv("SPEECH_VOICE", "preset-voice")
    settings.cache_clear()
    try:
        config = settings()
        assert (config.transcription_model, config.speech_model, config.speech_voice) == (
            "provider/transcription",
            "provider/speech",
            "preset-voice",
        )
    finally:
        settings.cache_clear()
