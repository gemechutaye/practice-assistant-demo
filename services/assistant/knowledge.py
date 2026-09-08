"""Versioned source retrieval combining pgvector and PostgreSQL text ranking."""

import hashlib
import math
import time

from .domain import Actor


def vector_literal(values: list[float]) -> str:
    if len(values) != 1536 or any(not math.isfinite(float(x)) for x in values):
        raise ValueError("Embedding must contain 1536 finite values")
    return "[" + ",".join(str(float(x)) for x in values) + "]"


class Knowledge:
    def __init__(self, store, models):
        self.store, self.models = store, models

    def search(self, actor: Actor, query: str, limit: int = 4) -> dict:
        started = time.monotonic()
        sources = self.store.get_sources(actor)
        if not sources:
            return {"sources": [], "method": "hybrid", "usage": {}}
        ids = [s["id"] for s in sources]
        hashes = {
            s["id"]: hashlib.sha256((s["title"] + "\n" + s["excerpt"]).encode()).hexdigest() for s in sources
        }
        with self.store.connection() as conn:
            existing = conn.execute(
                "SELECT source_id,content_hash,embedding_model FROM pa_source_vectors WHERE workspace_id=%s AND source_id=ANY(%s)",
                (actor.workspace_id, ids),
            ).fetchall()
        fresh = {
            r["source_id"]
            for r in existing
            if hashes.get(r["source_id"]) == r["content_hash"]
            and r["embedding_model"] == self.models.config.embedding_model
        }
        missing = [s for s in sources if s["id"] not in fresh]
        usage = {"total_tokens": 0}
        if missing:
            vectors, charged = self.models.embed([s["title"] + "\n" + s["excerpt"] for s in missing])
            usage["total_tokens"] += charged.get("total_tokens", 0)
            if "cost" in charged:
                usage["cost"] = charged["cost"]
            with self.store.connection() as conn:
                for source, vector in zip(missing, vectors, strict=True):
                    conn.execute(
                        """INSERT INTO pa_source_vectors(workspace_id,source_id,content_hash,embedding_model,embedding)
                      VALUES (%s,%s,%s,%s,%s::vector) ON CONFLICT(workspace_id,source_id)
                      DO UPDATE SET content_hash=excluded.content_hash,embedding_model=excluded.embedding_model,embedding=excluded.embedding,created_at=now()""",
                        (
                            actor.workspace_id,
                            source["id"],
                            hashes[source["id"]],
                            self.models.config.embedding_model,
                            vector_literal(vector),
                        ),
                    )
        vectors, charged = self.models.embed([query[:1500]])
        usage["total_tokens"] += charged.get("total_tokens", 0)
        if "cost" in charged:
            usage["cost"] = usage.get("cost", 0) + charged["cost"]
        with self.store.connection() as conn:
            # Scope filters are applied before either ranker receives candidates.
            rows = conn.execute(
                """SELECT s.id, 1-(v.embedding <=> %s::vector) AS similarity,
                ts_rank_cd(to_tsvector('english',s.title||' '||s.excerpt),plainto_tsquery('english',%s)) AS text_rank
              FROM pa_sources s JOIN pa_source_vectors v ON v.workspace_id=s.workspace_id AND v.source_id=s.id
              WHERE s.workspace_id=%s AND s.id=ANY(%s)""",
                (vector_literal(vectors[0]), query, actor.workspace_id, ids),
            ).fetchall()
        vector_order = sorted(rows, key=lambda r: float(r["similarity"]), reverse=True)
        text_order = sorted(
            (r for r in rows if r["text_rank"] > 0), key=lambda r: float(r["text_rank"]), reverse=True
        )
        scores = {}
        for ranking in (vector_order, text_order):
            for rank, row in enumerate(ranking, 1):
                scores[row["id"]] = scores.get(row["id"], 0) + 1 / (60 + rank)
        by_id = {s["id"]: s for s in sources}
        chosen = sorted(scores, key=scores.get, reverse=True)[: max(1, min(limit, 6))]
        return {
            "sources": [{**by_id[i], "retrieval_score": round(scores[i], 6)} for i in chosen],
            "method": "PostgreSQL text search + pgvector similarity",
            "embedding_model": self.models.config.embedding_model,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "usage": usage,
        }
