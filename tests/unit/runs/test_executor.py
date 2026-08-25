"""The executor, with nothing behind it.

Deliberately tested without a graph. A scheduling bug and a graph bug look identical once
they are combined, and the combined thing takes a minute to run — so the part that decides
what runs and when is exercised on work that does nothing but record that it happened.
"""

import threading
import time

import pytest

from runs.executor import QueueFullError, ThreadPoolRunExecutor, build_executor


@pytest.fixture
def executor():
    pool = ThreadPoolRunExecutor(pool_size=2, queue_limit=8)
    yield pool
    pool.shutdown()


def _wait_until(condition, timeout=5.0):
    """Poll rather than sleep a fixed amount, so a slow machine does not fail a test that
    a fast one passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


def test_submitted_work_is_executed(executor):
    done = threading.Event()

    executor.submit(done.set)

    assert done.wait(timeout=5.0)


def test_submitting_does_not_wait_for_the_work(executor):
    """The caller is inside a request. A submit that blocked would reintroduce the blocking
    request this whole change exists to remove.
    """
    release = threading.Event()
    started = threading.Event()

    def _slow():
        started.set()
        release.wait(timeout=5.0)

    executor.submit(_slow)

    assert started.wait(timeout=5.0)
    release.set()


def test_the_pool_does_not_exceed_its_size():
    """Two workers means two things at once, whatever is waiting behind them."""
    pool = ThreadPoolRunExecutor(pool_size=2, queue_limit=16)
    release = threading.Event()
    concurrent = []
    lock = threading.Lock()
    high_water = 0

    def _occupy():
        nonlocal high_water
        with lock:
            concurrent.append(1)
            high_water = max(high_water, len(concurrent))
        release.wait(timeout=5.0)
        with lock:
            concurrent.pop()

    try:
        for _ in range(6):
            pool.submit(_occupy)
        _wait_until(lambda: high_water >= 2)
        release.set()
    finally:
        pool.shutdown()

    assert high_water == 2


def test_work_that_raises_does_not_take_the_worker_with_it():
    """A pool whose thread dies on an exception silently loses capacity, and the run that
    caused it is exactly the run nobody was watching.
    """
    pool = ThreadPoolRunExecutor(pool_size=1, queue_limit=8)
    survived = threading.Event()

    def _explode():
        raise RuntimeError("the graph fell over")

    try:
        pool.submit(_explode)
        pool.submit(survived.set)

        assert survived.wait(timeout=5.0)
    finally:
        pool.shutdown()


def test_a_full_queue_refuses_rather_than_accepting_work_it_cannot_start():
    """The person who submits the last of a burst would otherwise wait half an hour without
    being told to come back.
    """
    pool = ThreadPoolRunExecutor(pool_size=1, queue_limit=2)
    release = threading.Event()

    try:
        for _ in range(2):
            pool.submit(lambda: release.wait(timeout=5.0))
        _wait_until(lambda: pool.in_flight == 2)

        with pytest.raises(QueueFullError):
            pool.submit(lambda: None)
    finally:
        release.set()
        pool.shutdown()


def test_the_refusal_says_how_full_the_queue_was():
    """So a client can be told to come back shortly rather than given a bare error."""
    pool = ThreadPoolRunExecutor(pool_size=1, queue_limit=1)
    release = threading.Event()

    try:
        pool.submit(lambda: release.wait(timeout=5.0))
        _wait_until(lambda: pool.in_flight == 1)

        with pytest.raises(QueueFullError) as refusal:
            pool.submit(lambda: None)
    finally:
        release.set()
        pool.shutdown()

    assert refusal.value.limit == 1
    assert refusal.value.depth == 1


def test_a_finished_run_frees_its_place_in_the_queue():
    """Otherwise the queue fills permanently and the deployment stops accepting runs after
    exactly `queue_limit` of them, forever.
    """
    pool = ThreadPoolRunExecutor(pool_size=1, queue_limit=1)

    try:
        pool.submit(lambda: None)
        assert _wait_until(lambda: pool.in_flight == 0)

        pool.submit(lambda: None)  # must not raise
    finally:
        pool.shutdown()


def test_work_that_raises_still_frees_its_place():
    """The failure path leaks a slot far more easily than the success path, and leaks the
    same way: silently, until the queue is permanently full.
    """
    pool = ThreadPoolRunExecutor(pool_size=1, queue_limit=1)

    def _explode():
        raise RuntimeError("no")

    try:
        pool.submit(_explode)

        assert _wait_until(lambda: pool.in_flight == 0)
    finally:
        pool.shutdown()


def test_the_executor_is_built_from_settings():
    from core.config import Settings
    from tests.secrets import TEST_JWT_SECRET

    settings = Settings(
        _env_file=None, openrouter_api_key="k", jwt_secret=TEST_JWT_SECRET, run_pool_size=2
    )
    pool = build_executor(settings)
    try:
        assert pool.in_flight == 0
    finally:
        pool.shutdown()
