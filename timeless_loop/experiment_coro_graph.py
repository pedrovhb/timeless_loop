from __future__ import annotations

import asyncio
import subprocess
import textwrap
from abc import abstractmethod
from asyncio import TimerHandle, AbstractEventLoop
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from itertools import count
from types import TracebackType
from typing import Coroutine, overload, Type, Generic, TypeVar, ClassVar

import networkx as nx
from networkx import MultiDiGraph

from timeless_loop import _P, _T, _T_contra, _T_co, timeless_event_loop_ctx

seq = iter(count())


def handle_repr(handle: TimerHandle) -> str:
    tb_str = textwrap.indent(
        "\n - ".join(
            f"{frame.filename}:{frame.lineno} - {frame.name}()"
            for frame in handle._source_traceback
        ),
        "  ",
    )
    return f"TimerHandle(callback={handle._callback}, when={handle._when:.3f} @\n - {tb_str})"


_NodeT = TypeVar("_NodeT")
_EdgeT = TypeVar("_EdgeT")


class AutoCounter:
    def __init__(self) -> None:
        self._count: int = 0

    def __call__(self) -> int:
        self._count += 1
        return self._count


@dataclass(frozen=True)
class Edge(Generic[_NodeT, _EdgeT]):
    label: str
    u: _NodeT
    v: _NodeT
    count: int = 0

    # Note the default factory isn't a function, but a class instance.
    # Each time a new instance of the class is created, its __call__ method
    # is called, which is what we want.
    sequence_number: int = field(default_factory=AutoCounter(), init=False)

    _instances: ClassVar[dict[tuple[str, _NodeT, _NodeT], Edge[_NodeT, _EdgeT]]] = {}

    def __new__(cls, label: str, u: _NodeT, v: _NodeT) -> Edge[_NodeT, _EdgeT]:
        key = (label, u, v)
        if key not in cls._instances:
            cls._instances[key] = super().__new__(cls)
        return cls._instances[key]

    @cached_property
    def key(self) -> tuple[str, _NodeT, _NodeT]:
        return self.label, self.u, self.v

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Edge):
            return NotImplemented
        return self.key == other.key


class CoroGraph(Generic[_NodeT, _EdgeT]):
    def __init__(self) -> None:
        self.coro_execution_stack: list[_CoroWrapper] = []
        self.coro_graph = MultiDiGraph()

    def add_node(self, node_for_adding: _NodeT, parent: _NodeT | None) -> None:
        self.coro_graph.add_node(node_for_adding)
        self._render_graph()

    def add_edge(self, u_of_edge: _NodeT, v_of_edge: _NodeT, edge_label: EdgeType) -> None:
        edge = Edge(edge_label, u_of_edge, v_of_edge)
        self.coro_graph.add_edge(u_of_edge, v_of_edge, key=edge.key, edge=edge, label=edge.label)
        self._render_graph()

    def remove_edge(self, u_of_edge: _NodeT, v_of_edge: _NodeT, edge_label: EdgeType) -> None:
        edge = Edge(edge_label, u_of_edge, v_of_edge)
        if self.coro_graph.has_edge(u_of_edge, v_of_edge, key=edge.key):
            self.coro_graph.remove_edge(u_of_edge, v_of_edge, key=edge.key)
        self._render_graph()

    @property
    def current_node(self):
        if self.coro_execution_stack:
            return self.coro_execution_stack[-1]

    @property
    def parent_node(self):
        if len(self.coro_execution_stack) > 1:
            return self.coro_execution_stack[-2]

    def _render_graph(self):
        # Write an image visualization of the graph with pygraphviz.
        # We use a modern theme with nice colors, spline-based edges,
        # and rounded rectangles for nodes with a modern monospaced
        # font.
        print(f"Writing graph to coro_graph.dot - {self}")
        identifier = next(seq)
        if self.current_node:
            self.coro_graph.nodes[self.current_node]["color"] = "green"
        if self.parent_node:
            self.coro_graph.nodes[self.parent_node]["color"] = "yellow"
        agraph = nx.nx_agraph.to_agraph(self.coro_graph)
        font_color = "#d8dee9"
        font_name = "Fira Code Bold"
        fill_color = "#3b4252"
        agraph.graph_attr.update(
            {
                "bgcolor": "#2e3440",
                "fontname": font_name,
                "fontsize": 14,
                "fontcolor": font_color,
                "rankdir": "LR",
                "splines": "spline",
                "overlap": "true",
                "nodesep": 0.5,
                "ranksep": 0.5,
                "pad": 0.5,
                "margin": 0,
            }
        )
        agraph.node_attr.update(
            {
                "shape": "rect",
                "style": "rounded",
                "color": font_color,
                "fillcolor": fill_color,
                "fontname": font_name,
                "fontsize": 14,
                "fontcolor": font_color,
                "margin": 0.1,
                "pad": 0.1,
            }
        )
        agraph.edge_attr.update(
            {
                "color": font_color,
                "fontname": font_name,
                "fontsize": 14,
                "fontcolor": font_color,
                "penwidth": 2,
                "label": lambda e: e.attr.get("edge").label.value,
            }
        )
        dot_fname = f"coro_graph_{identifier:0>4d}.dot"
        agraph.layout("neato")
        agraph.draw(dot_fname, format="dot")
        subprocess.run(["dot", "-Tpng", "-O", dot_fname])
        if self.current_node:
            self.coro_graph.nodes[self.current_node].pop("color")
        if self.parent_node:
            self.coro_graph.nodes[self.parent_node].pop("color")


class _CoroWrapper(Coroutine[_P, _T, _T_contra]):
    @overload
    @abstractmethod
    def throw(
        self,
        __typ: Type[BaseException],
        __val: BaseException | object = ...,
        __tb: TracebackType | None = ...,
    ) -> _T_co:
        ...

    @overload
    @abstractmethod
    def throw(
        self, __typ: BaseException, __val: None = ..., __tb: TracebackType | None = ...
    ) -> _T_co:
        ...

    def throw(self, __typ, __val=None, __tb=None):
        self._coro_graph.add_edge(
            self._coro_graph.coro_execution_stack[-1], self, EdgeType.ThrowedDuring
        )
        # todo have to pop?
        self._coro_graph.coro_execution_stack.pop()
        return self._original_coro.throw(__typ, __val, __tb)

    def close(self):
        self._coro_graph.add_edge(
            self._coro_graph.coro_execution_stack[-1], self, EdgeType.ClosedDuring
        )
        # todo have to pop?
        self._coro_graph.coro_execution_stack.pop()
        return self._original_coro.close()

    def __init__(
        self,
        original_coro: Coroutine[_P, _T, _T_contra],
        coro_graph: CoroGraph[Coroutine[_P, _T, _T_contra], EdgeType],
    ) -> None:
        self._original_coro = original_coro
        self._coro_graph = coro_graph

        self._children: list[_CoroWrapper] = []
        if parent_stack := self._coro_graph.coro_execution_stack:
            self._parent = parent_stack[-1]
        else:
            self._parent = None

        if self._parent:
            self._parent._children.append(self)
            # self._coro_graph.add_edge(self._parent, self, EdgeType.Created)
        print(f"Creating coro wrapper: {self}")

    def __await__(self) -> _T_contra:
        print(f"__await__ called on {self}")
        return self._original_coro.__await__()

    def send(self, __value) -> _T_contra:
        prev_in_stack = (
            self._coro_graph.coro_execution_stack[-1]
            if self._coro_graph.coro_execution_stack
            else None
        )
        self._coro_graph.coro_execution_stack.append(self)
        print(f"Send value {__value} to {self}")
        if prev_in_stack:
            self._coro_graph.add_edge(prev_in_stack, self, EdgeType.Awaited)
        else:
            print(f"prev_in_stack is None, {self} is the root coro")

        val = self._original_coro.send(__value)

        # assert self._coro_graph.coro_execution_stack.pop() is self
        # if prev_in_stack:
        #     self._coro_graph.add_edge(self, prev_in_stack, EdgeType.ReturnedTo)
        # self._coro_graph.remove_edge(self, prev_in_stack, EdgeType.Awaited)
        # else:
        #     print(f"end - prev_in_stack is None, {self} is the root coro")

        return val

    def __repr__(self) -> str:
        return f"<_CoroWrapper for {self._original_coro}>"


class EdgeType(str, Enum):
    Created = "created"
    Awaited = "awaited"
    ReturnedTo = "returned_to"
    Cancelled = "cancelled"
    ClosedDuring = "closed_during"
    ThrowedDuring = "throwed_during"


class TaskFactory:
    def __init__(self) -> None:
        self._coro_stack = []
        self._coro_graph = CoroGraph[_CoroWrapper, Edge[_CoroWrapper, EdgeType]]()

    def __call__(
        self, loop: AbstractEventLoop, coro: Coroutine[_P, _T, _T_contra]
    ) -> asyncio.Task[_T_contra]:
        return asyncio.Task(_CoroWrapper(coro, self._coro_graph), loop=loop)


async def main() -> None:
    from datetime import datetime

    # asyncio.get_event_loop().set_debug(True)
    start_time_loop = asyncio.get_event_loop().time()
    start_time_wall = datetime.now()

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

    print("Done!")
    print(f"Loop time: {asyncio.get_event_loop().time() - start_time_loop:.3f} seconds")
    print(f"Wall time: {(datetime.now() - start_time_wall).total_seconds():.3f} seconds")

    proc = await asyncio.create_subprocess_exec(
        "ls",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print(stdout.decode())
    print(stderr.decode())

    proc_shell = await asyncio.create_subprocess_shell(
        "echo $(pwd) && sleep 1 && date",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    print("Waiting for shell command to finish...")
    stdout, stderr = await proc_shell.communicate()
    print(stdout.decode())
    print(stderr.decode())

    await asyncio.gather(proc.wait(), proc_shell.wait())
    print("Shell commands test done!")
    print(f"Loop time: {asyncio.get_event_loop().time() - start_time_loop:.3f} seconds")
    print(f"Wall time: {(datetime.now() - start_time_wall).total_seconds():.3f} seconds")


async def run_deadlock_test() -> None:
    ev1 = asyncio.Event()
    ev2 = asyncio.Event()
    loop = asyncio.get_event_loop()

    async def waiter_1() -> None:
        print("Waiting for ev1")
        # ev1.set()
        await ev1.wait()
        print(f"Setting ev2")
        ev2.set()
        print("Ev2 set!")

    async def waiter_2() -> None:
        print("Waiting for ev2")
        await ev2.wait()
        print(f"Setting ev1")
        ev1.set()
        print("Ev1 set!")

    t1 = loop.create_task(waiter_1())
    t2 = loop.create_task(waiter_2())
    print("Awaiting tasks")
    await asyncio.gather(t1, t2)
    print("Done!")


if __name__ == "__main__":
    with timeless_event_loop_ctx():
        loop = asyncio.get_event_loop()
        factory = TaskFactory()
        loop.set_task_factory(factory)

        # loop.run_until_complete(main())
        loop.run_until_complete(run_deadlock_test())
