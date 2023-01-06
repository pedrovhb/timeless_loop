"""This modulde defines a class that can be used to create an event loop whose time runs instantly,
rather than after an actual clock. This is useful for testing code that uses asyncio.sleep() or
asyncio.wait_for() (or loop.call_later, etc.) to wait for a certain amount of time to pass.

Test code can use this class to run the event loop faster than real time, so tests don't take
all day to run.
"""

from __future__ import annotations

import asyncio
import functools
import heapq
import time
from asyncio import SelectorEventLoop, TimerHandle, tasks, AbstractEventLoop, coroutines
from asyncio.log import logger
from collections import deque
from functools import singledispatchmethod
from selectors import SelectSelector, SelectorKey
from types import TracebackType
from typing import *

MAXIMUM_SELECT_TIMEOUT = 24 * 3600


_P = ParamSpec("_P")
_T = TypeVar("_T")


class DeadlockError(Exception):
    """Raised when a deadlock is detected."""


class TimelessTask(tasks.Task):
    """A Task subclass with added instrumentation."""

    def __init__(self, coro: Awaitable, *, loop: AbstractEventLoop) -> None:
        super().__init__(coro, loop=loop)


class TimelessEventLoop(SelectorEventLoop):

    _scheduled: list[TimerHandle]
    _ready: deque[TimerHandle]
    _selector: SelectSelector
    _process_events: Callable[[List[Tuple[SelectorKey, int]]], None]
    _timer_cancelled_count: int
    _debug: bool
    _clock_resolution: float
    _stopping: bool

    def __init__(self, raise_on_deadlock: bool = False, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._raise_on_deadlock = raise_on_deadlock
        self._time = 0
        # asyncio.get_event_loop().set_task_factory(self._task_factory)

    def _task_factory(self, loop: AbstractEventLoop, coro: Awaitable[Any]) -> asyncio.Task:
        task = tasks.Task(loop, coro)
        # if task._source_traceback:
        #     del task._source_traceback[-1]
        return task

    def time(self) -> float:
        return self._time

    def _run_once(self):
        """This is a modified version of the _run_once() method from BaseEventLoop.

        It's 90% the same, but:

        - instead of calling select() with a timeout based on the next scheduled callback, it
        always calls select() with a timeout of 0, so it doesn't block at all.

        - If no callbacks are ready, it moves the time forward to the next scheduled callback.
        """
        _MIN_SCHEDULED_TIMER_HANDLES = 100
        _MIN_CANCELLED_TIMER_HANDLES_FRACTION = 0.5

        sched_count = len(self._scheduled)
        if (
            sched_count > _MIN_SCHEDULED_TIMER_HANDLES
            and self._timer_cancelled_count / sched_count > _MIN_CANCELLED_TIMER_HANDLES_FRACTION
        ):
            # Remove delayed calls that were cancelled if their number
            # is too high
            new_scheduled = []
            for handle in self._scheduled:
                if handle._cancelled:
                    handle._scheduled = False
                else:
                    new_scheduled.append(handle)

            heapq.heapify(new_scheduled)
            self._scheduled = new_scheduled
            self._timer_cancelled_count = 0
        else:
            # Remove delayed calls that were cancelled from head of queue.
            while self._scheduled and self._scheduled[0]._cancelled:
                self._timer_cancelled_count -= 1
                handle = heapq.heappop(self._scheduled)
                handle._scheduled = False

        timeout = 0

        event_list = self._selector.select(timeout)
        self._process_events(event_list)

        end_time = self.time() + self._clock_resolution
        while self._scheduled:
            handle = self._scheduled[0]
            if handle._when >= end_time:  # type: ignore[member-access]
                break
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False
            self._ready.append(handle)

        ntodo = len(self._ready)
        for i in range(ntodo):
            handle = self._ready.popleft()
            if handle._cancelled:
                continue
            if self._debug:
                try:
                    self._current_handle = handle
                    t0 = time.perf_counter()
                    handle._run()
                    dt = time.perf_counter() - t0
                    if dt >= self.slow_callback_duration:
                        logger.warning(f"Executing {handle} took {dt:%.3f} seconds")
                finally:
                    self._current_handle = None
            else:
                handle._run()

        if self._scheduled and not ntodo:
            # No ready callbacks this loop iteration; move time forward to next scheduled callback
            self._time = next(hd._when for hd in self._scheduled)  # type: ignore[member-access]

        is_deadlock = not self._scheduled and not self._ready and not self._stopping
        if is_deadlock and self._raise_on_deadlock:
            # for task in asyncio.all_tasks(self):
            #     task.print_stack()
            tasks_str = "\n".join(str(t) for t in asyncio.all_tasks(self))
            msg = f"Active tasks: {len(asyncio.all_tasks(self))}\n{tasks_str}"
            raise DeadlockError(f"{msg}\n\nNo scheduled or ready callbacks while loop is running")

        handle = None  # Needed to break cycles when an exception occurs.


class TimelessEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def __init__(self, raise_on_deadlock: bool = False, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._raise_on_deadlock = raise_on_deadlock

    def get_event_loop(self) -> TimelessEventLoop:
        loop = super().get_event_loop()
        if not isinstance(loop, TimelessEventLoop):
            loop = TimelessEventLoop(self._raise_on_deadlock)
            asyncio.set_event_loop(loop)
        return loop

    def new_event_loop(self) -> TimelessEventLoop:
        return TimelessEventLoop(self._raise_on_deadlock)


class _UseTimelessEventLoop:
    """Usable as a context manager to temporarily use the TimelessEventLoop.

    Can also be used to setup the TimelessEventLoopPolicy or restore the previous policy
    with setup_timeless_event_loop_policy or restore_event_loop_policy.
    """

    __slots__ = ("_previous_policy", "_raise_on_deadlock")

    def __init__(self, raise_on_deadlock: bool = True) -> None:
        self._previous_policy = None
        self._raise_on_deadlock = raise_on_deadlock

    def setup_timeless_event_loop_policy(self, raise_on_deadlock: bool = True) -> None:
        """Setup the TimelessEventLoopPolicy as the default policy."""
        self._raise_on_deadlock = raise_on_deadlock
        self._previous_policy = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(TimelessEventLoopPolicy(self._raise_on_deadlock))

    def restore_event_loop_policy(self) -> None:
        """Restore the previous event loop policy."""
        if self._previous_policy is None:
            raise RuntimeError("Timeless event loop not active.")
        asyncio.set_event_loop_policy(self._previous_policy)
        self._previous_policy = None

    __enter__ = setup_timeless_event_loop_policy

    def __call__(self, enabled: bool = True, raise_on_deadlock: bool = True) -> None:
        if enabled:
            self.setup_timeless_event_loop_policy(raise_on_deadlock)
        else:
            self.restore_event_loop_policy()
        return self

    def decorate(self, func: Callable[_P, _T]) -> Callable[_P, _T]:
        """Decorate a function to use the TimelessEventLoopPolicy."""
        # todo - remember args specific to this decorated fn
        @functools.wraps(func)
        def wrapper(*__args: _P.args, **__kwargs: _P.kwargs) -> _T:
            with self(enabled=True, raise_on_deadlock=self._raise_on_deadlock):
                return func(*__args, **__kwargs)

        return wrapper

    def __exit__(
        self,
        exception_type: Type[BaseException] | None,
        exception_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.restore_event_loop_policy()
        return False


use_timeless_event_loop = _UseTimelessEventLoop

__all__ = (
    "DeadlockError",
    "TimelessEventLoop",
    "TimelessEventLoopPolicy",
    "use_timeless_event_loop",
)

if __name__ == "__main__":

    async def main() -> None:
        print("Hello, world!")
        await asyncio.sleep(1)
        print("Goodbye, world!")

        async def task(n: int, slp: float) -> None:
            print(f"Starting task {n}")
            await asyncio.sleep(slp)
            print(f"Ending task {n}")

        # Intertwined tasks
        t1 = task(1, 1)
        t2 = task(2, 4)
        t3 = task(3, 3)
        await asyncio.gather(t1, t2, t3)

        asyncio.get_event_loop().call_later(1, lambda: print("Hello, world!"))
        asyncio.get_event_loop().call_later(2, lambda: print("Goodbye, world!"))
        asyncio.get_event_loop().call_later(1.5, lambda: print("In the middle!"))
        await asyncio.sleep(3)

        await asyncio.sleep(10e3)  # Sleep for 10000 seconds

        await asyncio.gather(
            task(1, 1),
            task(2, 2),
            task(3, 3),
            task(4, 2),
            task(5, 1),
            task(6, 4),
        )

    with use_timeless_event_loop:
        asyncio.run(main())

    # Or:
    # use_timeless_event_loop()
    # asyncio.run(main())
    # use_timeless_event_loop.restore_event_loop_policy()

    # Or:
    # use_timeless_event_loop.setup_timeless_event_loop_policy()
    # asyncio.run(main())
    # use_timeless_event_loop.restore_event_loop_policy()
