# timeless_loop

timeless_loop is a Python library that provides a custom asyncio event loop, allowing you to freeze time and avoid pesky delays while writing or testing async code. It does so by defining a subclass of the built-in `SelectorEventLoop`, which behaves nearly identically to the real one. It differs in that it does not actually wait for any time to pass; instead, it simply advances the loop's internal clock to the exact time of execution of the next scheduled callback when there are no immediately ready loop callbacks available. 

In addition, timeless_loop has the ability to detect and raise an exception when deadlocks occur in asyncio code. This helps to prevent your program from getting stuck in an infinite loop and allows you to easily track down and fix any issues.

## Installation

timeless_loop is available on PyPI and can be installed with `poetry`, `pip`, or your favorite package manager.

```bash
pip install timeless_loop
```

## Usage

The `use_timeless_event_loop` object provides a helper which can be called or used as a context manager to enable the use of the custom event loop. It can be used as follows:

```python
import asyncio
from timeless_loop import use_timeless_event_loop

async def main():
    # code here will run on the TimelessEventLoop
    pass

with use_timeless_event_loop:
    asyncio.run(main())

# Or, if you don't want to use a context manager:
# use_timeless_event_loop()
# asyncio.run(main())
# use_timeless_event_loop(False)
```

Alternatively, you can directly create and use a `TimelessEventLoop` instance:

```python
import asyncio
from timeless_loop import TimelessEventLoop

async def main():
    # code here will run on the TimelessEventLoop
    pass

loop = TimelessEventLoop()
loop.run_until_complete(main())
```

If a deadlock is detected by the TimelessEventLoop, a `DeadlockError` will be raised.

## License

timeless_loop is licensed under the MIT License. See the LICENSE file for more details.
