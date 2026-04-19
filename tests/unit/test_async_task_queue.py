"""Priority queue, cancellation TTL, and callback dispatch for AsyncUIHelper."""

import asyncio
import datetime

import pytest

import galliard.utils.async_task_queue as queue_module
from galliard.utils.async_task_queue import AsyncUIHelper


@pytest.fixture
async def fresh_queue(monkeypatch):
    """Reset the module-level queue/state between tests.

    ``AsyncUIHelper`` keeps the task_queue as module globals so each
    test would otherwise inherit leftovers from the last. On teardown
    we drop a ``None`` sentinel into the queue and yield control so any
    running ``process_queue`` coroutine breaks out of its loop before
    the event loop closes.
    """
    monkeypatch.setattr(queue_module, "task_queue", asyncio.PriorityQueue())
    monkeypatch.setattr(queue_module, "cancelled_task_ids", {})
    monkeypatch.setattr(queue_module, "process_queue_running", False)

    # Stub idle_add_once to run the callback synchronously; in production
    # it defers to the GLib main loop, which isn't running here.
    def sync_idle(fn, *args, **kwargs):
        fn(*args, **kwargs)
        return 0

    monkeypatch.setattr(queue_module, "idle_add_once", sync_idle)

    yield

    # Cancel any process_queue task still awaiting on the current loop so
    # we don't leave pending tasks at loop close.
    for task in list(asyncio.all_tasks()):
        coro = task.get_coro()
        if getattr(coro, "__name__", "") == "process_queue":
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


async def test_callback_receives_coroutine_result(fresh_queue):
    results = []

    async def work():
        return 42

    AsyncUIHelper.run_async_operation(work, results.append)

    # Yield repeatedly until the queue has been drained; the worker
    # task needs several trips through the loop to dequeue + run + dispatch.
    for _ in range(10):
        await asyncio.sleep(0)
    assert results == [42]


async def test_exception_callback_receives_none(fresh_queue):
    results = []

    async def work():
        raise RuntimeError("boom")

    AsyncUIHelper.run_async_operation(work, results.append)

    for _ in range(10):
        await asyncio.sleep(0)
    assert results == [None]


async def test_high_priority_task_runs_before_low(fresh_queue):
    order = []

    async def make_task(label):
        order.append(label)

    # Enqueue low first, then high. High has a lower priority number.
    AsyncUIHelper.run_async_operation(
        lambda: make_task("low"), None, task_priority=500,
    )
    AsyncUIHelper.run_async_operation(
        lambda: make_task("high"), None, task_priority=1,
    )

    for _ in range(10):
        await asyncio.sleep(0)
    assert order == ["high", "low"]


async def test_cancellation_skips_matching_task(fresh_queue):
    ran = []

    async def work():
        ran.append("ran")

    AsyncUIHelper.run_async_operation(work, None, task_id="doomed")
    AsyncUIHelper.cancel_async_operation("doomed")

    for _ in range(10):
        await asyncio.sleep(0)
    assert ran == []


async def test_cancellation_only_skips_matching_id(fresh_queue):
    ran = []

    async def work(label):
        ran.append(label)

    AsyncUIHelper.run_async_operation(
        lambda: work("doomed"), None, task_id="doomed",
    )
    AsyncUIHelper.run_async_operation(
        lambda: work("survivor"), None, task_id="survivor",
    )
    AsyncUIHelper.cancel_async_operation("doomed")

    for _ in range(10):
        await asyncio.sleep(0)
    assert ran == ["survivor"]


async def test_cancellation_ttl_drops_stale_entries(fresh_queue, monkeypatch):
    """After 60+ seconds the cancelled-id is expired, not held forever."""
    AsyncUIHelper.cancel_async_operation("ancient")
    assert "ancient" in queue_module.cancelled_task_ids

    # Fast-forward time past the 60s TTL by rewriting the stored timestamp.
    queue_module.cancelled_task_ids["ancient"] = (
        datetime.datetime.now().timestamp() - 120
    )

    async def work():
        return "ok"

    AsyncUIHelper.run_async_operation(work, None, task_id="unrelated")
    for _ in range(10):
        await asyncio.sleep(0)

    # Processing the queue runs the TTL cleanup sweep.
    assert "ancient" not in queue_module.cancelled_task_ids


async def test_run_in_background_returns_task(fresh_queue):
    """The decorator form creates a plain asyncio.Task."""

    class Host:
        @AsyncUIHelper.run_in_background
        async def method(self):
            return "result"

    task = Host().method()
    assert isinstance(task, asyncio.Task)
    assert await task == "result"


async def test_run_in_background_swallows_exceptions(fresh_queue):
    class Host:
        @AsyncUIHelper.run_in_background
        async def method(self):
            raise RuntimeError("boom")

    task = Host().method()
    # Exception is caught; task returns None instead of propagating.
    assert await task is None
