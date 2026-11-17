import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { BASE, inr } from "../api";
import { PageTitle } from "../components/ui.jsx";

const AGENTS = ["Planner", "Research", "Budget", "Reviewer"];
const DOT = { running: "bg-saffron animate-pulse", done: "bg-good", failed: "bg-bad", idle: "bg-line" };

function EventRow({ e }) {
  const tool = e.type === "tool_call";
  const tone = e.status === "warn" || e.status === "over" || e.status === "rejected" || e.status === "failed" || e.status === "error" ? "text-bad" : "";
  return (
    <li className="fade border-b border-line/60 py-2 text-sm">
      <div className="flex gap-2">
        <span className="w-20 shrink-0 text-xs text-muted">{new Date(e.ts).toLocaleTimeString()}</span>
        <span className="w-24 shrink-0 text-xs font-semibold uppercase tracking-wide text-teal">{e.agent || "System"}</span>
        <div className="min-w-0 flex-1">
          <p className={tone}>
            {tool && <span className="mr-1 rounded bg-saffron/15 px-1.5 py-0.5 text-xs font-semibold text-saffron">tool</span>}
            {e.type === "decision" && <span className="mr-1 rounded bg-teal/15 px-1.5 py-0.5 text-xs font-semibold text-teal">decision</span>}
            {e.type === "revision" && <span className="mr-1 rounded bg-bad/15 px-1.5 py-0.5 text-xs font-semibold text-bad">revision</span>}
            {e.message}
          </p>
          {tool && e.data && (
            <details className="mt-1 text-xs text-muted">
              <summary className="cursor-pointer">input, output ({e.data.duration_ms ?? 0} ms, {e.status})</summary>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-paper p-2">{"input: " + JSON.stringify(e.data.input, null, 1) + "\noutput: " + JSON.stringify(e.data.output, null, 1)}</pre>
            </details>
          )}
        </div>
      </div>
    </li>
  );
}

export default function Monitor() {
  const { tripId, executionId } = useParams();
  const [events, setEvents] = useState([]);
  const [conn, setConn] = useState("connecting");
  const endRef = useRef(null);

  useEffect(() => {
    setEvents([]); setConn("connecting");
    const es = new EventSource(`${BASE}/agents/activity/${executionId}`);
    const seen = new Set();
    es.onopen = () => setConn("live");
    es.onmessage = (m) => {
      const e = JSON.parse(m.data);
      if (e.seq !== undefined) { if (seen.has(e.seq)) return; seen.add(e.seq); }
      setEvents((prev) => [...prev, e]);
      if (e.type === "done") { setConn("finished"); es.close(); }
    };
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) setConn("closed"); else setConn("reconnecting"); };
    return () => es.close();
  }, [executionId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [events.length]);

  const view = useMemo(() => {
    const agents = Object.fromEntries(AGENTS.map((a) => [a, { status: "idle", task: "Waiting" }]));
    const checks = [];
    let revisions = 0, final = null, needs = null, error = null, maxRev = 3, humanWaiting = false;
    for (const e of events) {
      if (e.type === "agent_status" && agents[e.agent]) agents[e.agent] = { status: e.status, task: e.task || e.message };
      if (e.type === "budget_check") checks.push(e.data);
      if (e.type === "revision") { revisions = e.data.revision; maxRev = e.data.max; }
      if (e.type === "awaiting_approval") humanWaiting = true;
      if (e.type === "needs_input") needs = e.message;
      if (e.type === "error") error = e.message;
      if (e.type === "done") final = e;
    }
    return { agents, checks, revisions, final, needs, error, maxRev, humanWaiting };
  }, [events]);

  const feed = events.filter((e) => !(e.type === "agent_status" && e.status === "done" && !e.duration_ms && false));

  return (
    <div className="fade space-y-6">
      <PageTitle title="Agent activity" sub={`Live from the backend · ${conn}`}>
        <Link to={`/trips/${tripId}`} className="btn">Open itinerary</Link>
      </PageTitle>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {AGENTS.map((a) => (
          <div key={a} className="card py-4">
            <div className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${DOT[view.agents[a].status] || DOT.idle}`} /><h2 className="font-semibold">{a} agent</h2></div>
            <p className="mt-1 text-xs uppercase tracking-wide text-muted">{view.agents[a].status}</p>
            <p className="mt-1 truncate text-sm text-muted" title={view.agents[a].task}>{view.agents[a].task}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <h2 className="mb-2 font-display text-xl">Execution log</h2>
          <ul className="max-h-[32rem] overflow-auto" aria-live="polite">
            {feed.length === 0 && <li className="text-sm text-muted">Waiting for the first event…</li>}
            {feed.map((e, i) => <EventRow key={e.seq ?? i} e={e} />)}
            <div ref={endRef} />
          </ul>
        </section>

        <aside className="space-y-4">
          <section className="card">
            <h2 className="font-display text-xl">Budget validation</h2>
            {view.checks.length === 0 && <p className="mt-2 text-sm text-muted">No budget check yet.</p>}
            <ul className="mt-2 space-y-2">
              {view.checks.map((c, i) => (
                <li key={i} className={`rounded-lg border px-3 py-2 text-sm ${c.within_budget ? "border-good/50" : "border-bad/50"}`}>
                  <p className="font-semibold">Attempt {c.attempt}: {inr(c.total)} {c.budget ? `of ${inr(c.budget)}` : ""}</p>
                  <p className={c.within_budget ? "text-good" : "text-bad"}>{c.within_budget ? `Within budget, ${inr(c.remaining)} left` : `Over by ${inr(-c.remaining)}`}</p>
                </li>
              ))}
            </ul>
          </section>
          <section className="card">
            <h2 className="font-display text-xl">Revisions</h2>
            <p className="mt-2 text-sm">{view.revisions} of {view.maxRev} used</p>
          </section>
          {view.humanWaiting && <section className="card border-saffron"><p className="font-semibold">Your turn</p><p className="mb-3 text-sm text-muted">The agents finished. Review and approve the plan.</p><Link to={`/trips/${tripId}`} className="btn btn-primary">Review itinerary</Link></section>}
          {view.needs && <p role="alert" className="card border-bad text-sm text-bad">{view.needs} <Link className="underline" to="/plan">Start again</Link></p>}
          {view.error && <p role="alert" className="card border-bad text-sm text-bad">{view.error}</p>}
        </aside>
      </div>
    </div>
  );
}
