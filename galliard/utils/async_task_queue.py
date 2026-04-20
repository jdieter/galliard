#!/usr/bin/env python3

import asyncio
import datetime
import functools
import logging

from galliard.utils.glib import idle_add_once

task_queue = asyncio.PriorityQueue()
cancelled_task_ids = {}
process_queue_running = False

async def process_queue():
    """Drain the priority queue, running each coroutine and dispatching its result."""
    global task_queue
    global process_queue_running
    global cancelled_task_ids

    process_queue_running = True
    while True:
        item = await task_queue.get()
        if item is None:
            break

        _, timestamp, task_id, async_func, callback, args, kwargs = item
        if task_id in cancelled_task_ids:
            await asyncio.sleep(0)
            continue
        # Expire cancellations on a TTL. We can't key the cleanup off the
        # current item's timestamp because task_queue is a PriorityQueue:
        # a higher-priority task enqueued after a cancellation can be
        # dequeued before the task it cancels, so the cancellation must
        # outlive the matching low-priority enqueue.
        now = datetime.datetime.now().timestamp()
        for cid, cancel_time in list(cancelled_task_ids.items()):
            if now - cancel_time > 60:
                del cancelled_task_ids[cid]
        try:
            result = await async_func(*args, **kwargs)
            if callback:
                def call_callback(r=result, cb=callback):
                    cb(r)
                idle_add_once(call_callback)
        except Exception as e:
            logging.error("Error in async operation: %s", e)
            if callback:
                def call_callback_error(cb=callback):
                    cb(None)
                idle_add_once(call_callback_error)
        await asyncio.sleep(0)
        logging.debug('Tasks count: %i', len(asyncio.all_tasks()))

    process_queue_running = False


class AsyncUIHelper:
    """Priority-queued asyncio helper for kicking off UI work off the main path."""

    @staticmethod
    def run_in_background(func):
        """Decorate an async method so calling it schedules the coroutine.

        Usage::

            @AsyncUIHelper.run_in_background
            async def my_async_method(self):
                ...
        """

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            async def wrapped_func():
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    logging.error("Error in async operation: %s", e)
                    return None

            return asyncio.create_task(wrapped_func())

        return wrapper

    @staticmethod
    def run_glib_idle_async(async_func, *args, **kwargs):
        """Schedule ``async_func`` as an asyncio task from a GLib idle callback."""

        def idle_callback():
            asyncio.create_task(async_func(*args, **kwargs))

        idle_add_once(idle_callback)

    @staticmethod
    def cancel_async_operation(task_id):
        """Mark ``task_id`` as cancelled; matching queue items will be skipped."""
        global cancelled_task_ids
        cancelled_task_ids[task_id] = datetime.datetime.now().timestamp()

    @staticmethod
    def run_async_operation(async_func, callback=None, *args, **kwargs):
        """Queue ``async_func(*args, **kwargs)`` and dispatch ``callback(result)`` when done.

        Pulls ``task_priority`` (default 99; lower runs sooner) and ``task_id``
        (for :meth:`cancel_async_operation`) out of ``kwargs`` before forwarding
        the rest to ``async_func``. The callback runs on the GLib main loop.
        """
        global task_queue
        global process_queue_running

        priority = kwargs.pop("task_priority", 99)
        task_id = kwargs.pop("task_id", None)

        task_queue.put_nowait(
            (
                priority,
                datetime.datetime.now().timestamp(),
                task_id,
                async_func,
                callback,
                args,
                kwargs,
            )
        )

        if not process_queue_running:
            asyncio.create_task(process_queue())
