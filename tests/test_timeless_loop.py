from __future__ import annotations

import asyncio
import contextlib
import io
import random
from asyncio import AbstractEventLoopPolicy, DefaultEventLoopPolicy
from typing import AsyncIterator, List, Tuple, Type

import pytest

from timeless_loop import TimelessEventLoopPolicy

random.seed(0)
random_state = random.getstate()
random.setstate(random_state)


async def _test_loop_times_and_order() -> List[Tuple[float, str]]:
    """Test that the loop time is always the same and that the order of execution is correct.

    Run through a series of interleaved async functions and generators, and check that the
    loop time is always the same and that the order of execution is correct. Feel free
    to suggest more ideas to make things as messy and convoluted as possible.

    Currently, tests:
        - Async generators
        - Async iterables
        - Async context managers
        - Coroutines
        - Tasks
        - Events
        - loop.call_later
        - await asyncio.sleep()
    """

    initial_loop_time = asyncio.get_event_loop().time()
    output: list[tuple[float, str]] = []

    def record_output(message: str) -> None:
        t = asyncio.get_event_loop().time() - initial_loop_time
        output.append((t, message))

    @contextlib.asynccontextmanager
    async def open_file(filename: str, mode: str) -> AsyncIterator[io.StringIO]:
        record_output(f"Opening file {filename} with mode {mode}")
        f = io.StringIO()
        try:
            record_output("Yielding file")
            await asyncio.sleep(random.uniform(0, 1) * 0.1)
            yield f
            record_output("Closing file")
        finally:
            record_output(f"Closing file {filename}")
            f.close()

    # Async generator
    async def generate_random_numbers(n: int) -> AsyncIterator[int]:
        record_output("Starting async generator")
        for i in range(n):
            await asyncio.sleep(random.uniform(0, 1) * 0.1)
            record_output(f"Yielding random number {i}")
            await asyncio.sleep(0)
            yield random.randint(1, 10)

    # Async iterable
    class RandomNumberIterable:
        def __init__(self, n: int) -> None:
            record_output(f"RandomNumberIterable.__init__")
            self.n = n

        def __aiter__(self) -> RandomNumberIterable:
            record_output(f"RandomNumberIterable.__aiter__")
            return self

        async def __anext__(self) -> int:
            if self.n > 0:
                self.n -= 1
                await asyncio.sleep(random.uniform(0, 1) * 0.1)
                record_output(f"RandomNumberIterable.__anext__")
                return random.randint(1, 10)
            else:
                record_output(f"RandomNumberIterable.__anext__ StopAsyncIteration")
                raise StopAsyncIteration

    # Coroutine 1
    async def coroutine_1() -> None:
        record_output("Starting coroutine 1")
        await asyncio.sleep(0.1)
        record_output("Finishing coroutine 1")

    # Coroutine 2
    async def coroutine_2() -> None:
        record_output("Starting coroutine 2")
        await asyncio.sleep(0.2)
        record_output("Finishing coroutine 2")

    # Coroutine 3
    async def coroutine_3():
        record_output("Starting coroutine 3")
        await asyncio.sleep(0.3)
        record_output("Finishing coroutine 3")

    event = asyncio.Event()
    condition = asyncio.Condition()

    async def waiter():
        record_output("Waiting for event")
        await event.wait()
        record_output("Event set")

    ts = [asyncio.create_task(waiter()) for _ in range(3)]
    asyncio.get_event_loop().call_later(0.4, event.set)

    # Start coroutine 1 as a task
    task1 = asyncio.create_task(coroutine_1())

    # Start coroutine 2 as a future
    future2 = asyncio.ensure_future(coroutine_2())

    # Use async context manager to open a file
    async with open_file("test.txt", "w") as f:
        # Use async generator to write random numbers to file
        async for num in generate_random_numbers(5):
            f.write(str(num) + "\n")

    async for num in RandomNumberIterable(5):
        await asyncio.sleep(random.uniform(0, 1) * 0.1)
        record_output(str(num))

    # Wait for coroutine 2 to finish
    await future2

    # Set event and notify all waiting coroutines
    async with condition:
        condition.notify_all()

    # Start coroutine 3 with overlapping execution
    await asyncio.gather(coroutine_3(), task1, *ts)

    return output


@pytest.mark.parametrize(
    ("loop_policy", "tolerance"),
    # ((TimelessEventLoopPolicy, 0),),
    ((TimelessEventLoopPolicy, 0), (DefaultEventLoopPolicy, 0.02)),
)
def test_loop_times_and_order(loop_policy: Type[AbstractEventLoopPolicy], tolerance: float) -> None:
    random.setstate(random_state)

    loop = loop_policy().new_event_loop()
    output = loop.run_until_complete(_test_loop_times_and_order())

    expected_output = [
        (0.0, "Opening file test.txt with mode w"),
        (0.0, "Yielding file"),
        (0.0, "Waiting for event"),
        (0.0, "Waiting for event"),
        (0.0, "Waiting for event"),
        (0.0, "Starting coroutine 1"),
        (0.0, "Starting coroutine 2"),
        (0.08444218515250482, "Starting async generator"),
        (0.1, "Finishing coroutine 1"),
        (0.16023762544653508, "Yielding random number 0"),
        (0.16428606326461284, "Yielding random number 1"),
        (0.2, "Finishing coroutine 2"),
        (0.2128788329208941, "Yielding random number 2"),
        (0.30965883241291126, "Yielding random number 3"),
        (0.3679970363584144, "Yielding random number 4"),
        (0.3679970363584144, "Closing file"),
        (0.3679970363584144, "Closing file test.txt"),
        (0.3679970363584144, "RandomNumberIterable.__init__"),
        (0.3679970363584144, "RandomNumberIterable.__aiter__"),
        (0.4, "Event set"),
        (0.4, "Event set"),
        (0.4, "Event set"),
        (0.4184657219401534, "RandomNumberIterable.__anext__"),
        (0.4324403004368213, "5"),
        (0.4419233767845069, "RandomNumberIterable.__anext__"),
        (0.5406492968878082, "5"),
        (0.5939056602966609, "RandomNumberIterable.__anext__"),
        (0.6841222553406192, "10"),
        (0.7151370122725524, "RandomNumberIterable.__anext__"),
        (0.8050208410693518, "2"),
        (0.873419234260896, "RandomNumberIterable.__anext__"),
        (0.929400602162386, "8"),
        (0.929400602162386, "RandomNumberIterable.__anext__ StopAsyncIteration"),
        (0.929400602162386, "Starting coroutine 3"),
        (1.229400602162386, "Finishing coroutine 3"),
    ]

    assert len(output) == len(expected_output)
    for (t1, s1), (t2, s2) in zip(output, expected_output):
        # print((t1 - t2, s1))
        # Tolerance is necessary for the real time event loop, since there'll
        # be some fluctuation in the time taken to execute each step.
        # For the timeless loop, the time taken to execute each step should be
        # deterministic and exactly the same across executions, so the tolerance
        # is set to 0.
        assert abs(t1 - t2) <= tolerance
        assert s1 == s2


@pytest.mark.skip(reason="Expected to fail, and non-deterministic")
async def test_httpx():
    # This was mostly an exploration of how third-party libraries
    # would interact with the event loop. In the case of httpx,
    # there's a slight incompatibility - the anyio library under
    # the hood checks for timeouts with `if loop.time() >= self._deadline`.
    # Since the loop time is exactly the time at which a given task is scheduled,
    # this check will always return True, and the timeout will always be triggered.
    # The fix is to just use `if loop.time() > self._deadline` instead.
    # This is a problem with the anyio library, not with the event loop; I'll be
    # submitting a (-1 character) PR. I think the authors of anyio should be fine
    # with it, since it'll have effectively no impact on real-world usage.

    # import httpx
    #
    # client = httpx.AsyncClient()
    # response = await client.get("https://httpbin.org/get")
    # print(response.json())
    #
    # tasks = [asyncio.create_task(client.get("https://httpbin.org/get")) for _ in range(5)]
    # responses = await asyncio.gather(*tasks)
    # for response in responses:
    #     print(response.json())
    pass  # Test commented out because annoying typing errors
