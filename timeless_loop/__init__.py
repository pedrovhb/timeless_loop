"""This modulde defines a class that can be used to create an event loop whose time runs instantly,
rather than after an actual clock. This is useful for testing code that uses asyncio.sleep() or
asyncio.wait_for() (or loop.call_later, etc.) to wait for a certain amount of time to pass.

Test code can use this class to run the event loop faster than real time, so tests don't take
all day to run.
"""

from __future__ import annotations

import asyncio
import heapq
import selectors
import time
import typing
from asyncio import AbstractEventLoop, SelectorEventLoop
from asyncio.log import logger
from collections import deque
from contextlib import contextmanager
from selectors import SelectorKey, SelectSelector
from typing import Callable, List, Optional, Tuple

MAXIMUM_SELECT_TIMEOUT = 24 * 3600


class _TimerHandleProtocol(typing.Protocol):
    """Protocol class for typing validation.

    Pyright doesn't look into internal attributes for the TimerHandle
    class. We shouldn't either, but the standard library asyncio loop
    implementation does, and we're copying that, so ¯\\(ツ)/¯
    """

    _cancelled: bool
    _scheduled: bool
    _when: float

    def when(self) -> float:
        ...

    def _run(self) -> None:
        ...


class TimelessEventLoop(SelectorEventLoop):
    _scheduled: list[_TimerHandleProtocol]
    _ready: deque[_TimerHandleProtocol]
    _selector: SelectSelector
    _process_events: Callable[[List[Tuple[SelectorKey, int]]], None]
    _timer_cancelled_count: int
    _debug: bool
    _clock_resolution: float
    _stopping: bool

    def __init__(self, selector: selectors.BaseSelector | None = None) -> None:
        super().__init__(selector=selector)
        self._time: float = 0.0

    def time(self) -> float:
        return self._time

    def _run_once(self) -> None:
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
            new_scheduled: list[_TimerHandleProtocol] = []
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
            if handle.when() >= end_time:
                break
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False
            self._ready.append(handle)

        ntodo = len(self._ready)
        for _ in range(ntodo):
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
            next_time = next(hd.when() for hd in self._scheduled)
            logger.debug(
                f"No further callbacks at t={self.time()};"
                f"moving time forward to next callback time t={next_time}"
            )
            self._time = next_time

        handle = None  # Needed to break cycles when an exception occurs.


class TimelessEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def __init__(self) -> None:
        super().__init__()
        self._loop: Optional[AbstractEventLoop] = None

    def get_event_loop(self) -> AbstractEventLoop:
        if not self._loop:
            self.set_event_loop(self.new_event_loop())
        assert self._loop is not None
        return self._loop

    def set_event_loop(self, loop: AbstractEventLoop | None) -> None:
        self._loop = loop

    def new_event_loop(self) -> TimelessEventLoop:
        return TimelessEventLoop()


@contextmanager
def timeless_loop_ctx() -> typing.Iterator[None]:
    """Context manager that sets up a timeless event loop policy for the duration of the context.

    Usage:

        with timeless_loop_ctx():
            asyncio.run(main())
    """
    previous_policy = asyncio.get_event_loop_policy()
    try:
        policy = TimelessEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        yield
    finally:
        asyncio.set_event_loop_policy(previous_policy)


__all__ = ("TimelessEventLoop", "TimelessEventLoopPolicy", "timeless_loop_ctx")
