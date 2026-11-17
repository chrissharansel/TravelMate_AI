"""Run context: real-time event bus + persisted execution logs + logged tool calls.
Every event shown in the UI is created here from something the backend actually did."""
import asyncio, json, logging, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("travelmate")
now = lambda: datetime.now(timezone.utc)


def preview(obj: Any, limit: int = 1500) -> Any:
    """JSON-safe, size-limited copy for logs."""
    def conv(o):
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if isinstance(o, (list, tuple)):
            return [conv(x) for x in o]
        if isinstance(o, dict):
            return {str(k): conv(v) for k, v in o.items()}
        return o
    data = conv(obj)
    text = json.dumps(data, default=str, ensure_ascii=False)
    return data if len(text) <= limit else text[:limit] + f"... [truncated {len(text) - limit} chars]"


class Channel:
    def __init__(self):
        self.events: list[dict] = []
        self.cond = asyncio.Condition()
        self.done = False


class EventBus:
    def __init__(self):
        self.channels: dict[str, Channel] = {}

    def open(self, execution_id: str) -> Channel:
        return self.channels.setdefault(execution_id, Channel())

    async def publish(self, execution_id: str, event: dict):
        ch = self.open(execution_id)
        async with ch.cond:
            ch.events.append(event)
            if event["type"] == "done":
                ch.done = True
            ch.cond.notify_all()

    async def stream(self, execution_id: str):
        ch = self.channels.get(execution_id)
        if ch is None:
            return
        i = 0
        while True:
            async with ch.cond:
                while i >= len(ch.events) and not ch.done:
                    try:
                        await asyncio.wait_for(ch.cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        yield None            # heartbeat
                batch = ch.events[i:]
                finished = ch.done
            for e in batch:
                yield e
            i += len(batch)
            if finished and i >= len(ch.events):
                return


bus = EventBus()


class Step:
    def __init__(self): self.output = None


class RunContext:
    def __init__(self, repo, user_id: str, trip_id: str, execution_id: str, bus_: EventBus = bus):
        self.repo, self.user_id, self.trip_id, self.execution_id, self.bus = repo, user_id, trip_id, execution_id, bus_
        self.seq = 0
        self.bus.open(execution_id)

    async def emit(self, type: str, agent: str | None = None, status: str | None = None, message: str = "",
                   data: dict | None = None, task: str | None = None, input: Any = None, output: Any = None,
                   duration_ms: int | None = None):
        self.seq += 1
        ts = now()
        event = dict(seq=self.seq, ts=ts.isoformat(), execution_id=self.execution_id, trip_id=self.trip_id, type=type,
                     agent=agent, status=status, message=message, task=task, data=data or {})
        try:
            await self.repo.insert("agent_execution_logs", dict(
                execution_id=self.execution_id, trip_id=self.trip_id, seq=self.seq, agent=agent, task=task,
                input=preview(input, 4000) if input is not None else None,
                output=preview(output, 4000) if output is not None else None,
                status=status, timestamp=ts, duration_ms=duration_ms, event_type=type, event=event))
        except Exception as e:            # logging must never break a run
            log.warning("could not persist log: %s", e)
        await self.bus.publish(self.execution_id, event)

    @asynccontextmanager
    async def step(self, agent: str, task: str, input: Any = None):
        st, t0 = Step(), time.perf_counter()
        await self.emit("agent_status", agent, "running", task, task=task, input=input)
        try:
            yield st
        except Exception as e:
            await self.emit("agent_status", agent, "failed", f"{task} failed: {e}", task=task,
                            duration_ms=int((time.perf_counter() - t0) * 1000))
            raise
        await self.emit("agent_status", agent, "done", task, task=task, output=st.output,
                        duration_ms=int((time.perf_counter() - t0) * 1000))

    async def tool(self, agent: str, name: str, fn: Callable, **kwargs):
        """Run a registered Python tool (in a worker thread) and log input, output, time and status."""
        t0 = time.perf_counter()
        try:
            result = await asyncio.to_thread(fn, **kwargs)
        except Exception as e:
            await self.emit("tool_call", agent, "error", f"{name} failed: {e}", task=f"tool:{name}", input=kwargs,
                            data=dict(tool=name, input=preview(kwargs, 600), error=str(e)),
                            duration_ms=int((time.perf_counter() - t0) * 1000))
            raise
        ms = int((time.perf_counter() - t0) * 1000)
        await self.emit("tool_call", agent, "ok", f"{name}()", task=f"tool:{name}", input=kwargs, output=result,
                        data=dict(tool=name, input=preview(kwargs, 600), output=preview(result, 900), duration_ms=ms),
                        duration_ms=ms)
        return result
