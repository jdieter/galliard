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
            await asyncio.sleep(0)  # Yield control to the event loop
            continue
        # Expire cancellations older than the TTL. We can't key the cleanup off
        # the current item's timestamp because task_queue is a PriorityQueue:
        # a higher-priority task enqueued after a cancellation can be dequeued
        # before the task it cancels, so the cancellation must outlive it.
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
            print(f"Error in async operation: {e}")
            if callback:
                def call_callback_error(cb=callback):
                    cb(None)
                idle_add_once(call_callback_error)
        await asyncio.sleep(0)  # Yield control to the event loop
        logging.debug('Tasks count: %i', len(asyncio.all_tasks()))

    process_queue_running = False


class AsyncUIHelper:
    """Helper class for handling asynchronous operations in UI widgets"""

    @staticmethod
    def run_in_background(func):
        """
        Decorator to run a coroutine in the background and handle exceptions

        Usage:
            @AsyncUIHelper.run_in_background
            async def my_async_method(self):
                result = await some_async_operation()
                return result
        """

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            async def wrapped_func():
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    print(f"Error in async operation: {e}")
                    return None

            # Create a task
            return asyncio.create_task(wrapped_func())

        return wrapper

    @staticmethod
    def run_glib_idle_async(async_func, *args, **kwargs):
        """
        Run an asynchronous operation using GLib.idle_add
        to ensure it runs in the GTK main loop

        Args:
            async_func: Async function to call
            *args, **kwargs: Arguments to pass to async_func
        """

        def idle_callback():
            # Create and run the async task from within the GTK main loop
            # if asyncio.get_event_loop().is_running():
            asyncio.create_task(async_func(*args, **kwargs))

        # Schedule the task creation to happen in the GTK main loop
        idle_add_once(idle_callback)

    @staticmethod
    def cancel_async_operation(task_id):
        """
        Cancel a queued async operation by its task ID

        This ensures that any queued operations with the given task ID will be
        skipped when processed.

        Args:
            task_id: ID of the task to cancel
        """
        global cancelled_task_ids
        cancelled_task_ids[task_id] = datetime.datetime.now().timestamp()

    @staticmethod
    def run_async_operation(async_func, callback=None, *args, **kwargs):
        """
        Queue an artwork request to be processed asynchronously

        Args:
            async_func: Async function to call for artwork retrieval
            callback: Function to call with the result
            *args, **kwargs: Arguments to pass to async_func
        """
        global task_queue
        global process_queue_running

        # check for priority in kwargs and set default if not provided
        priority = kwargs.pop("task_priority", 99)
        task_id = kwargs.pop("task_id", None)

        # Add the item to the queue
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
            # Start processing the queue if not already running, unless event loop hasn't
            # been setup yet (e.g., during initial setup)
            # if asyncio.get_event_loop().is_running():
            asyncio.create_task(process_queue())
