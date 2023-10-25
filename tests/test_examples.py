import asyncio
import math

from examples.example_long_intertwined_coros import example_long_intertwined_coros
from timeless_loop import timeless_loop_ctx


def test_example_long_intertwined_coros() -> None:
    with timeless_loop_ctx():
        loop_time, wall_time = asyncio.run(example_long_intertwined_coros())
        assert loop_time > wall_time
        assert loop_time == 1011.000
        assert math.isclose(wall_time, 0.001, abs_tol=0.1)
