import asyncio
import contextlib
import io
import random
from asyncio import DefaultEventLoopPolicy, AbstractEventLoopPolicy
from typing import Type, List, Tuple

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
    async def open_file(filename, mode):
        record_output(f"Opening file {filename} with mode {mode}")
        f = io.StringIO()
        try:
            record_output("Yielding file")
            await asyncio.sleep(random.uniform(0, 1))
            yield f
            record_output("Closing file")
        finally:
            record_output(f"Closing file {filename}")
            f.close()

    # Async generator
    async def generate_random_numbers(n):
        record_output("Starting async generator")
        for i in range(n):
            await asyncio.sleep(random.uniform(0, 1))
            record_output(f"Yielding random number {i}")
            await asyncio.sleep(0)
            yield random.randint(1, 10)

    # Async iterable
    class RandomNumberIterable:
        def __init__(self, n):
            record_output(f"RandomNumberIterable.__init__")
            self.n = n

        def __aiter__(self):
            record_output(f"RandomNumberIterable.__aiter__")
            return self

        async def __anext__(self):
            if self.n > 0:
                self.n -= 1
                await asyncio.sleep(random.uniform(0, 1))
                record_output(f"RandomNumberIterable.__anext__")
                return random.randint(1, 10)
            else:
                record_output(f"RandomNumberIterable.__anext__ StopAsyncIteration")
                raise StopAsyncIteration

    # Coroutine 1
    async def coroutine_1():
        record_output("Starting coroutine 1")
        await asyncio.sleep(1)
        record_output("Finishing coroutine 1")

    # Coroutine 2
    async def coroutine_2():
        record_output("Starting coroutine 2")
        await asyncio.sleep(2)
        record_output("Finishing coroutine 2")

    # Coroutine 3
    async def coroutine_3():
        record_output("Starting coroutine 3")
        await asyncio.sleep(3)
        record_output("Finishing coroutine 3")

    event = asyncio.Event()
    condition = asyncio.Condition()

    async def waiter():
        record_output("Waiting for event")
        await event.wait()
        record_output("Event set")

    ts = [asyncio.create_task(waiter()) for _ in range(3)]
    asyncio.get_event_loop().call_later(4, event.set)

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
        await asyncio.sleep(random.uniform(0, 1))
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
    ((TimelessEventLoopPolicy, 0), (DefaultEventLoopPolicy, 0.2)),
)
def test_loop_times_and_order(loop_policy: Type[AbstractEventLoopPolicy], tolerance: float) -> None:
    random.setstate(random_state)

    loop = loop_policy().new_event_loop()
    output = loop.run_until_complete(_test_loop_times_and_order())

    expected_output = [
        (0, "Opening file test.txt with mode w"),
        (0, "Yielding file"),
        (0, "Waiting for event"),
        (0, "Waiting for event"),
        (0, "Waiting for event"),
        (0, "Starting coroutine 1"),
        (0, "Starting coroutine 2"),
        (0.8444218515250481, "Starting async generator"),
        (1, "Finishing coroutine 1"),
        (1.6023762544653506, "Yielding random number 0"),
        (1.6428606326461281, "Yielding random number 1"),
        (2, "Finishing coroutine 2"),
        (2.1287883292089407, "Yielding random number 2"),
        (3.096588324129112, "Yielding random number 3"),
        (3.679970363584143, "Yielding random number 4"),
        (3.679970363584143, "Closing file"),
        (3.679970363584143, "Closing file test.txt"),
        (3.679970363584143, "RandomNumberIterable.__init__"),
        (3.679970363584143, "RandomNumberIterable.__aiter__"),
        (4, "Event set"),
        (4, "Event set"),
        (4, "Event set"),
        (4.184657219401533, "RandomNumberIterable.__anext__"),
        (4.324403004368212, "5"),
        (4.419233767845068, "RandomNumberIterable.__anext__"),
        (5.406492968878081, "5"),
        (5.939056602966608, "RandomNumberIterable.__anext__"),
        (6.84122255340619, "10"),
        (7.151370122725523, "RandomNumberIterable.__anext__"),
        (8.050208410693516, "2"),
        (8.734192342608956, "RandomNumberIterable.__anext__"),
        (9.294006021623856, "8"),
        (9.294006021623856, "RandomNumberIterable.__anext__ StopAsyncIteration"),
        (9.294006021623856, "Starting coroutine 3"),
        (12.294006021623856, "Finishing coroutine 3"),
    ]

    assert len(output) == len(expected_output)
    for (t1, s1), (t2, s2) in zip(output, expected_output):
        assert abs(t1 - t2) <= tolerance
        assert s1 == s2


# skip
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
    import httpx

    client = httpx.AsyncClient()
    response = await client.get("https://httpbin.org/get")
    print(response.json())

    tasks = [asyncio.create_task(client.get("https://httpbin.org/get")) for _ in range(5)]
    responses = await asyncio.gather(*tasks)
    for response in responses:
        print(response.json())
