# timeless_loop

timeless_loop is a Python library that provides a custom asyncio event loop, allowing you to freeze time and avoid pesky delays while writing or testing async code.
It does so by defining a subclass of the standard library `SelectorEventLoop`, which behaves nearly identically to the real one.
It differs in that it does not actually wait for any time to pass; instead, it simply advances the loop's internal clock to the exact time of execution of the next scheduled callback when there are no immediately ready loop callbacks available.
This allows you to run code that uses asyncio's `sleep` and `wait` functions without having to wait for the actual time to pass, without having to change any lines of code between the real and the fake time event loop.


## Installation

timeless_loop is available on PyPI and can be installed with `poetry`, `pip`, or your favorite package manager.

```bash
pip install timeless_loop
```

## Usage

The recommended way of setting the TimelessEventLoop is through setring the loop policy with `asyncio.set_event_loop_policy`. It can be used as follows:

```python
import asyncio

async def main():
    # code here will run on the TimelessEventLoop
    pass

if __name__ == "__main__":
    
    
    # Set the event loop policy to use the TimelessEventLoop
    from timeless_loop import TimelessEventLoopPolicy
    
    asyncio.set_event_loop_policy(TimelessEventLoopPolicy())
    asyncio.run(main())
    
    # OR:
    # Use the context manager:
    import timeless_loop
    
    with timeless_loop:
        asyncio.run(main())

```

## License

timeless_loop is licensed under the MIT License. See the LICENSE file for more details.
