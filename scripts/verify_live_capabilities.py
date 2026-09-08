"""Bounded paid checks with synthetic audio, a fresh office, and sanitized reports."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import wave

from dotenv import dotenv_values

from services.assistant.config import Settings
from services.assistant.domain import Actor
from services.assistant.knowledge import Knowledge
from services.assistant.model_router import Models
from services.assistant.store import Store
from services.assistant.telemetry import configure, recent_spans


class BoundedModels(Models):
    def __init__(self, config, maximum_cost=1.0):
        super().__init__(config)
        self.maximum_cost = maximum_cost
        self.requests = []

    def _check_budget(self):
        known_cost = sum(float(r["cost_usd"]) for r in self.requests if r["cost_usd"] is not None)
        if len(self.requests) >= 8 or known_cost >= self.maximum_cost * 0.75:
            raise RuntimeError("The bounded verification request budget was reached")

    def _post(self, path, body):
        self._check_budget()
        body = dict(body)
        if "max_tokens" in body:
            body["max_tokens"] = min(body["max_tokens"], 400)
        started = time.monotonic()
        try:
            result = super()._post(path, body)
        except Exception as error:
            self.requests.append(
                {
                    "endpoint": path,
                    "model": body.get("model"),
                    "cost_usd": None,
                    "error_type": type(error).__name__,
                    "passed": False,
                }
            )
            raise
        usage = result.get("usage") or {}
        self.requests.append(
            {
                "endpoint": path,
                "model": result.get("model", body.get("model")),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "tokens": usage.get("total_tokens"),
                "cost_usd": usage.get("cost"),
            }
        )
        return result

    def _post_audio(self, body):
        self._check_budget()
        started = time.monotonic()
        try:
            audio, usage = super()._post_audio(body)
        except Exception as error:
            self.requests.append(
                {
                    "endpoint": "audio/speech",
                    "model": body.get("model"),
                    "cost_usd": None,
                    "error_type": type(error).__name__,
                    "passed": False,
                }
            )
            raise
        self.requests.append(
            {
                "endpoint": "audio/speech",
                "model": body["model"],
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "cost_usd": None,
                "input_characters": len(body["input"]),
                "generation_id_present": bool(usage.get("request_id")),
            }
        )
        return audio, usage


def convert_to_wav(source: Path, target: Path):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(source), str(target)],
            check=True,
            capture_output=True,
        )
    with wave.open(str(target)) as audio:
        assert audio.getframerate() == 16000 and audio.getnchannels() == 1 and audio.getnframes() > 0
        return round(audio.getnframes() / audio.getframerate(), 3)


def contains_words(transcript, words):
    normalized = set(re.findall(r"[a-z]+", transcript.casefold()))
    return all(word in normalized for word in words)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    private = dotenv_values(args.env_file)
    config = Settings(
        database_url=args.database_url,
        openrouter_key=private["OPENROUTER_API_KEY"],
        supabase_url="",
        supabase_anon_key="",
        planner_model=private.get("PLANNER_MODEL", "openai/gpt-5.6-terra"),
        fast_model=private.get("FAST_MODEL", "google/gemini-3.5-flash-lite"),
        content_model=private.get("CONTENT_MODEL", "anthropic/claude-sonnet-5"),
        embedding_model=private.get("EMBEDDING_MODEL", "openai/text-embedding-3-small"),
        transcription_model=private.get("TRANSCRIPTION_MODEL", "openai/whisper-large-v3-turbo"),
        speech_model=private.get("SPEECH_MODEL", "hexgrad/kokoro-82m"),
        speech_voice=private.get("SPEECH_VOICE", "af_heart"),
    )
    output = Path("artifacts/verification")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "data": "Synthetic speech and fictional office records only",
        "cases": {},
        "budget_limit_usd": 1.0,
        "maximum_requests": 8,
        "maximum_output_tokens_per_request": 400,
    }
    models = BoundedModels(config)
    store = Store(config.database_url)
    workspace_id = None
    started = time.monotonic()
    try:
        fixture_aiff, fixture_wav = output / "synthetic-request.aiff", output / "synthetic-request.wav"
        fixture_text = "Prepare tomorrow and check the missing paperwork."
        subprocess.run(
            ["/usr/bin/say", "-o", str(fixture_aiff), fixture_text], check=True, capture_output=True
        )
        duration = convert_to_wav(fixture_aiff, fixture_wav)
        transcript, usage = models.transcribe(fixture_wav.read_bytes())
        assert contains_words(transcript, ["tomorrow", "paperwork"])
        report["cases"]["speech_input"] = {
            "passed": True,
            "fixture_text": fixture_text,
            "transcript": transcript,
            "audio_seconds": duration,
            "model": config.transcription_model,
            "usage": usage,
        }
        print(json.dumps({"stage": "speech_input", "passed": True}), flush=True)

        spoken_text = "Your demonstration calendar is ready for tomorrow."
        generated, usage = models.speak(spoken_text)
        assert len(generated) > 500
        (output / "spoken-response.mp3").write_bytes(generated)
        spoken_wav = output / "spoken-response.wav"
        output_duration = convert_to_wav(output / "spoken-response.mp3", spoken_wav)
        recognized_output, roundtrip_usage = models.transcribe(spoken_wav.read_bytes())
        assert contains_words(recognized_output, ["calendar", "tomorrow"])
        report["cases"]["speech_output_roundtrip"] = {
            "passed": True,
            "requested_text": spoken_text,
            "recognized_output": recognized_output,
            "playable_mp3_bytes": len(generated),
            "audio_seconds": output_duration,
            "model": config.speech_model,
            "voice": config.speech_voice,
            "speech_usage": usage,
            "transcription_usage": roundtrip_usage,
        }
        print(json.dumps({"stage": "speech_output_roundtrip", "passed": True}), flush=True)

        workspace_id = store.create_workspace("live-capability-verification")
        actor = store.get_actor(workspace_id, "live-capability-verification", "doctor")
        knowledge = Knowledge(store, models)
        preparation = knowledge.search(
            actor, "When should the intake forms arrive ahead of the appointment?", 3
        )
        assert "source-paperwork-policy" in [s["id"] for s in preparation["sources"]]
        editor = Actor(workspace_id, actor.user_id, "editor")
        pricing = knowledge.search(editor, "Why is the individual cost discussed in a consultation?", 3)
        assert "source-scar-pricing" in [s["id"] for s in pricing["sources"]]
        assert all(s["provenance"] == "public" for s in pricing["sources"])
        with store.connection() as conn:
            vectors = conn.execute(
                "SELECT count(*) AS n,min(vector_dims(embedding)) AS dimensions FROM pa_source_vectors WHERE workspace_id=%s",
                (workspace_id,),
            ).fetchone()
            extension = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        assert vectors["n"] >= 5 and vectors["dimensions"] == 1536
        report["cases"]["retrieval"] = {
            "passed": True,
            "method": preparation["method"],
            "embedding_model": config.embedding_model,
            "preparation_source_ids": [s["id"] for s in preparation["sources"]],
            "pricing_source_ids": [s["id"] for s in pricing["sources"]],
            "stored_vectors": vectors["n"],
            "dimensions": vectors["dimensions"],
            "pgvector_version": extension["extversion"],
            "preparation_ms": preparation["duration_ms"],
            "pricing_ms": pricing["duration_ms"],
            "preparation_usage": preparation["usage"],
            "pricing_usage": pricing["usage"],
        }
        print(json.dumps({"stage": "real_pgvector_retrieval", "passed": True}), flush=True)

        configure()
        completion = models.complete(
            [{"role": "user", "content": "Reply with the single word ready."}], None, config.fast_model, 40
        )
        assert "ready" in str(completion.message.get("content", "")).casefold()
        spans = recent_spans()
        actual_spans = [s for s in spans if s["name"] == "model.complete"]
        assert actual_spans and actual_spans[-1]["attributes"]["gen_ai.request.model"] == config.fast_model
        report["cases"]["telemetry"] = {
            "passed": True,
            "span": actual_spans[-1],
            "actual_model": completion.model,
            "usage": completion.usage,
            "export": "Observed in-process OpenTelemetry span exporter; external OTLP collector not exercised",
        }
        report["passed"] = True
    except Exception as error:
        report["failure"] = {
            "error_type": type(error).__name__,
            "code": getattr(error, "code", None),
            "note": "The check failed. Provider payloads and credentials are intentionally omitted.",
        }
    finally:
        if workspace_id:
            with store.connection() as conn:
                conn.execute("DELETE FROM pa_workspaces WHERE id=%s", (workspace_id,))
        models.client.close()
        costs = [float(r["cost_usd"]) for r in models.requests if r["cost_usd"] is not None]
        report.update(
            requests=models.requests,
            known_cost_usd=round(sum(costs), 8) if costs else None,
            cost_unavailable_requests=sum(r["cost_usd"] is None for r in models.requests),
            elapsed_seconds=round(time.monotonic() - started, 3),
        )
        (output / "live-capabilities.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "cases": list(report["cases"]),
                "requests": len(models.requests),
                "known_cost_usd": report["known_cost_usd"],
                "failure": report.get("failure"),
            }
        ),
        flush=True,
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
