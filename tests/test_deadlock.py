import asyncio

import pytest

from timeless_loop import DeadlockError, TimelessEventLoop, use_timeless_event_loop

# use_timeless_event_loop = pytest.fixture(scope="session")(timeless_loop_fixture)
# use_timeless_event_loop(raise_on_deadlock=True)(True)
# Add more tests for deadlocks triggered in different ways


@use_timeless_event_loop(raise_on_deadlock=True).decorate
async def _test_deadlocker_a():

    event_a = asyncio.Event()
    event_b = asyncio.Event()

    async def task_a():
        await event_a.wait()
        event_b.set()

    async def task_b():
        await event_b.wait()
        event_a.set()

    print("Starting tasks")
    await asyncio.gather(task_a(), task_b())


@use_timeless_event_loop(raise_on_deadlock=True).decorate
async def _test_deadlocker_b():

    lock_a = asyncio.Lock()
    lock_b = asyncio.Lock()

    async def task_a():
        async with lock_a:
            await asyncio.sleep(0.1)
            async with lock_b:
                pass

    async def task_b():
        async with lock_b:
            await asyncio.sleep(0.1)
            async with lock_a:
                pass

    print("Starting tasks")
    await asyncio.gather(task_a(), task_b())


@use_timeless_event_loop(raise_on_deadlock=True).decorate
async def _test_deadlocker_c():

    event_a = asyncio.Event()
    event_b = asyncio.Event()

    async def task_a():
        await event_a.wait()
        await event_b.wait()

    async def task_b():
        await event_b.wait()
        await event_a.wait()

    print("Starting tasks")
    await asyncio.gather(task_a(), task_b())


@use_timeless_event_loop(raise_on_deadlock=True).decorate
async def _test_deadlocker_d():

    lock = asyncio.Lock()

    async def task():
        async with lock:
            await lock.acquire()

    print("Starting tasks")
    await task()


@use_timeless_event_loop(raise_on_deadlock=True).decorate
async def _test_deadlocker_e():

    lock = asyncio.Lock()

    async def task():
        await lock.acquire()
        await lock.acquire()

    print("Starting tasks")
    await task()


@use_timeless_event_loop(raise_on_deadlock=True).decorate
async def _test_deadlocker_f():

    event = asyncio.Event()

    async def task():
        await event.wait()
        await event.wait()

    print("Starting tasks")
    await task()


def test_deadlocker_a():
    with pytest.raises(DeadlockError):
        asyncio.run(_test_deadlocker_a())


def test_deadlocker_b():
    with pytest.raises(DeadlockError):
        asyncio.run(_test_deadlocker_b())


def test_deadlocker_c():
    with pytest.raises(DeadlockError):
        asyncio.run(_test_deadlocker_c())


def test_deadlocker_d():
    with pytest.raises(DeadlockError):
        asyncio.run(_test_deadlocker_d())


def test_deadlocker_e():
    with pytest.raises(DeadlockError):
        asyncio.run(_test_deadlocker_e())
