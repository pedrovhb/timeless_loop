"""
This example defines some intertwining coroutines that execute in a 
deterministic order, and then runs them in a TimelessEventLoop to
demonstrate that they execute in the same order, but much faster.
It compares the event loop time at each step with the actual
wall clock time, and shows that the event loop time is much faster.
"""

from __future__ import annotations

import asyncio
import time

from timeless_loop import timeless_loop_ctx


async def example_long_intertwined_coros() -> tuple[float, float]:
    starting_time_loop = asyncio.get_event_loop().time()
    starting_time_wall = time.perf_counter()

    async def _print_after_delay(value: str, delay: float) -> None:
        await asyncio.sleep(delay)
        print(f"Print after delay: {value}")

    d = asyncio.create_task(_print_after_delay("And a vicious circle", 3))
    await asyncio.sleep(0.1)
    c = asyncio.create_task(_print_after_delay("Then endless streams of cars", 2))
    b = asyncio.create_task(_print_after_delay("First there's the morning", 1))
    await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)

    await asyncio.gather(b, c, d)
    await asyncio.sleep(1000)
    f = asyncio.create_task(_print_after_delay("    (Deep Poetry® by Github Copilot™)", 8))
    e = asyncio.create_task(_print_after_delay("Of never ending days", 4))
    await f
    await e
    loop_time = asyncio.get_event_loop().time() - starting_time_loop
    wall_time = time.perf_counter() - starting_time_wall
    print(f"Loop time: {loop_time :.3f}")
    print(f"Wall time: {wall_time :.3f}")
    return loop_time, wall_time


if __name__ == "__main__":
    with timeless_loop_ctx():
        asyncio.run(example_long_intertwined_coros())

    # Results:
    # Print after delay: First there's the morning
    # Print after delay: Then endless streams of cars
    # Print after delay: And a vicious circle
    # Print after delay: Of never ending days
    # Print after delay:   (Deep poetry by Github Copilot)
    # Loop time: 1011.000
    # Wall time: 0.001
