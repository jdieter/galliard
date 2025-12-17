#!/usr/bin/env python3

import asyncio
import datetime
import functools
import logging

from galliard.utils.glib import idle_add_once

task_queue = asyncio.PriorityQueue()
process_queue_running = False


async def process_queue():
    global task_queue, process_queue_running

    process_queue_running = True
    while True:
        item = await task_queue.get()
        if item is None:
            break

        _, _, async_func, callback, args, kwargs = item
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
    def run_async_operation(async_func, callback=None, *args, **kwargs):
        """
        Queue an artwork request to be processed asynchronously

        Args:
            async_func: Async function to call for artwork retrieval
            callback: Function to call with the result
            *args, **kwargs: Arguments to pass to async_func
        """
        global process_queue_running

        # check for priority in kwargs and set default if not provided
        priority = kwargs.pop("task_priority", 99)

        # Add the item to the queue
        task_queue.put_nowait(
            (
                priority,
                datetime.datetime.now().timestamp(),
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
