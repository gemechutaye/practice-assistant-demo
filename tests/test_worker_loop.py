from services.assistant.worker import run_loop


class ControlledStop:
    def __init__(self, after_waits):
        self.after_waits = after_waits
        self.waits = []

    def is_set(self):
        return len(self.waits) >= self.after_waits

    def wait(self, seconds):
        self.waits.append(seconds)
        return self.is_set()


def test_idle_polling_is_bounded_and_real_work_restores_responsiveness():
    stop = ControlledStop(after_waits=7)
    outcomes = iter([False, False, False, False, False, False, True, True, False])
    calls = []

    def step():
        calls.append(True)
        return next(outcomes)

    run_loop(stop, step)
    assert stop.waits == [1, 2, 4, 8, 15, 15, 1]
    assert len(calls) == 9  # Consecutive real jobs ran without an idle sleep.


def test_repeated_database_errors_back_off_without_exposing_error_payload(caplog):
    stop = ControlledStop(after_waits=4)

    def fail():
        raise ConnectionError("private database connection detail")

    run_loop(stop, fail)
    assert stop.waits == [1, 2, 4, 8]
    assert "ConnectionError" in caplog.text
    assert "private database" not in caplog.text


def test_once_mode_performs_one_poll_without_idle_wait():
    stop = ControlledStop(after_waits=1)
    calls = []
    run_loop(stop, lambda: calls.append(True), once=True)
    assert calls == [True]
    assert stop.waits == []
