# timeless_loop

timeless_loop is a Python library that provides a custom asyncio event loop, allowing you to freeze time and avoid pesky delays while writing or testing async code. It does so by defining a subclass of the built-in `SelectorEventLoop`, which behaves nearly identically to the real one. It differs in that it does not actually wait for any time to pass; instead, it simply advances the loop's internal clock to the exact time of execution of the next scheduled callback when there are no immediately ready loop callbacks available. 

In addition, timeless_loop has the ability to detect and raise an exception when deadlocks occur in asyncio code. This helps to prevent your program from getting stuck in an infinite loop and allows you to easily track down and fix any issues. This is experimental, and thus subject to bugs. It is disabled by default.

## Installation

timeless_loop is available on PyPI and can be installed with `poetry`, `pip`, or your favorite package manager.

```bash
pip install timeless_loop
```

## Usage

The recommended way of setting the TimelessEventLoop is through setring the loop policy with `asyncio.set_event_loop_policy`. It can be used as follows:

```python
import asyncio
from timeless_loop import TimelessEventLoopPolicy

async def main():
    # code here will run on the TimelessEventLoop
    pass

asyncio.set_event_loop_policy(TimelessEventLoopPolicy(raise_on_deadlock=False))
asyncio.run(main())

```

Alternatively, you can directly create and use a `TimelessEventLoop` instance:

```python
import asyncio
from timeless_loop import TimelessEventLoop

async def main():
    # code here will run on the TimelessEventLoop
    pass

loop = TimelessEventLoop(raise_on_deadlock=False)
loop.run_until_complete(main())
```

If a deadlock is detected by the TimelessEventLoop, a `DeadlockError` will be raised if the loop was created with the raise_on_deadlock flag set to True.

## License

timeless_loop is licensed under the MIT License. See the LICENSE file for more details.
