"""A separate process claims durable jobs and resumes interrupted work."""

import argparse
import logging
import signal
import threading

from .agent import Agent
from .config import settings
from .domain import DomainError, apply_handoff
from .jobs import Jobs
from .model_router import Models, ModelError
from .store import Store

log = logging.getLogger("practice_assistant.worker")


def process_outbox(store):
    # Commit a short lease claim before calling the handler. Its receipt and
    # fence are checked in the same transaction as the target record mutation.
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_outbox SET status='failed',error='Event retry limit reached' WHERE attempts>=8 AND (status='queued' OR (status='processing' AND lease_until<now()))"
        )
        row = conn.execute(
            "SELECT * FROM pa_outbox WHERE attempts<8 AND (status='queued' OR (status='processing' AND lease_until<now())) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if not row:
            return False
        row = conn.execute(
            "UPDATE pa_outbox SET status='processing',lease_generation=lease_generation+1,lease_until=now()+interval '60 seconds',attempts=attempts+1 WHERE id=%s RETURNING *",
            (row["id"],),
        ).fetchone()
    try:
        actor = store.get_actor(str(row["workspace_id"]), row["user_id"], row["role"])
        payload = row["payload"]
        apply_handoff(
            store,
            actor,
            payload["event_id"],
            payload["event_type"],
            payload["record_id"],
            outbox_id=str(row["id"]),
            outbox_generation=row["lease_generation"],
        )
        with store.connection() as conn:
            conn.execute(
                "UPDATE pa_outbox SET status='completed',lease_until=NULL WHERE id=%s AND lease_generation=%s",
                (row["id"], row["lease_generation"]),
            )
    except DomainError as error:
        with store.connection() as conn:
            conn.execute(
                "UPDATE pa_outbox SET status='failed',error=%s,lease_until=NULL WHERE id=%s AND lease_generation=%s",
                (str(error), row["id"], row["lease_generation"]),
            )
    return True


def process_one(store, jobs, models, cfg):
    job = jobs.claim(cfg.worker_lease_seconds)
    if not job:
        return process_outbox(store)
    done = threading.Event()

    def heartbeat():
        while not done.wait(20):
            try:
                if not jobs.renew(job, cfg.worker_lease_seconds):
                    return
            except Exception:
                log.warning("lease_renewal_failed run_id=%s", job["run_id"])

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        Agent(store, jobs, models, cfg).run(job)
    except DomainError as error:
        if error.code != "lease_lost":
            try:
                jobs.update(
                    job,
                    status="failed",
                    error=str(error),
                    answer="This request could not finish. Review the recorded progress and try again.",
                )
                jobs.finish_job(job)
            except DomainError:
                pass
        log.warning("run_stopped run_id=%s code=%s", job["run_id"], error.code)
    except Exception as error:
        # Never dump environment/configuration or provider bodies into public logs.
        log.error("run_failed run_id=%s error_type=%s", job["run_id"], type(error).__name__)
        try:
            message = (
                str(error)
                if isinstance(error, ModelError)
                else "An internal operation failed. Earlier verified actions remain recorded."
            )
            jobs.update(
                job,
                status="failed",
                error=message,
                answer="The run stopped before it could finish. Its recorded progress is available for inspection.",
            )
            jobs.finish_job(job)
        except DomainError:
            pass
    finally:
        done.set()
        thread.join(timeout=1)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = settings()
    store = Store(cfg.database_url)
    jobs = Jobs(store)
    models = Models(cfg)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            worked = process_one(store, jobs, models, cfg)
        except Exception as error:
            log.error("worker_poll_failed error_type=%s", type(error).__name__)
            worked = False
        if args.once:
            break
        if not worked:
            stopped.wait(1)


if __name__ == "__main__":
    main()
