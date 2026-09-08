"""Small paired routing comparison; accuracy is checked, not assumed from price."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from services.assistant.config import settings
from services.assistant.model_router import Models
from services.assistant.public_content import parse_model_json

SYSTEM = "Classify an office request. Return only JSON with route: content for solely public content work, report for solely counting/reporting, planner for any scheduling, memory, private office work, or mixed request."
CASES = [
    ("Draft a public informational post from the public scar consultation note.", "content"),
    ("Count open tasks grouped by owner.", "report"),
    ("Move the engineering meeting around clinic appointments and remember my preference.", "planner"),
]


def evaluate(model, prompt, expected):
    client = Models(settings())
    started = time.monotonic()
    result = client.complete(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        None,
        model,
        100,
        {"type": "json_object"},
    )
    actual = parse_model_json(result.message["content"]).get("route")
    return {
        "requested_model": model,
        "reported_model": result.model,
        "provider": result.provider,
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
        "tokens": result.usage.get("total_tokens"),
        "cost": result.usage.get("cost"),
        "wall_ms": round((time.monotonic() - started) * 1000),
    }


if __name__ == "__main__":
    config = settings()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(evaluate, model, prompt, expected)
            for prompt, expected in CASES
            for model in (config.fast_model, config.planner_model)
        ]
        rows = [f.result() for f in futures]
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Three paired routing requests; not a full-workflow benchmark or statistical performance claim.",
        "cases": rows,
        "passed": all(r["passed"] for r in rows),
    }
    p = Path("artifacts/verification/model-routes.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
