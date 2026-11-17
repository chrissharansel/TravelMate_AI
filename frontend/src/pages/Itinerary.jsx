import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { approveTrip, errText, getTrip, inr, reviseTrip, saveTrip } from "../api";
import { ErrorBox, PageTitle, Spinner, StatusBadge } from "../components/ui.jsx";

const KIND = { activity: "border-teal", meal: "border-saffron", travel: "border-line" };

function Stat({ label, value, tone }) {
  return <div className="card py-4"><p className="text-xs uppercase tracking-wide text-muted">{label}</p><p className={`font-display text-2xl ${tone || ""}`}>{value}</p></div>;
}

export default function Itinerary() {
  const { tripId } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [version, setVersion] = useState(null);
  const [feedback, setFeedback] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback((v) => getTrip(tripId, v).then(setData).catch((e) => setErr(errText(e))), [tripId]);
  useEffect(() => { load(version); }, [load, version]);

  if (err && !data) return <ErrorBox>{err}</ErrorBox>;
  if (!data) return <Spinner label="Loading trip" />;

  const { trip, itinerary: row, overview, versions } = data;
  const running = trip.status === "planning" || trip.status === "revising";
  if (!row) {
    return (
      <div className="card">
        <p className="mb-3">{running ? "The agents are still working." : trip.status === "needs_info" ? "More information is needed to plan this trip." : "No itinerary was produced."}</p>
        <Link className="btn btn-primary" to={trip.latest_execution_id ? `/trips/${tripId}/activity/${trip.latest_execution_id}` : "/plan"}>{running ? "Watch the agents" : "See what happened"}</Link>
      </div>
    );
  }

  const it = row.itinerary, c = it.cost;
  const latest = versions[0]?.version;
  const viewing = row.version;
  const meals = [...new Map(it.days.flatMap((d) => d.items.filter((i) => i.kind === "meal")).map((m) => [m.name, m])).values()];
  const parts = [["Accommodation", c.accommodation], ["Transport", c.transport], ["Food", c.food], ["Activities", c.activities]];

  const act = (fn, ok) => async () => {
    setBusy(true); setErr(""); setMsg("");
    try { await fn(); setMsg(ok); await load(version); } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const revise = (body) => async () => {
    setBusy(true); setErr("");
    try { const r = await reviseTrip(tripId, body); nav(`/trips/${tripId}/activity/${r.execution_id}`); } catch (e) { setErr(errText(e)); setBusy(false); }
  };

  return (
    <div className="fade space-y-6">
      <PageTitle title={`${it.destination}, ${it.days.length} days`} sub={`${it.travelers} traveler(s) · version ${viewing}${viewing !== latest ? " (older version)" : ""}`}>
        <div className="flex items-center gap-2"><StatusBadge status={trip.status} />
          <Link className="btn" to={`/trips/${tripId}/activity/${trip.latest_execution_id}`}>Agent activity</Link></div>
      </PageTitle>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Estimated total" value={inr(c.total)} />
        <Stat label="Budget" value={inr(c.budget)} />
        <Stat label={c.remaining >= 0 ? "Remaining" : "Over budget"} value={inr(Math.abs(c.remaining ?? 0))} tone={c.remaining >= 0 ? "text-good" : "text-bad"} />
        <Stat label="Agent attempts" value={row.attempts.length} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="space-y-4 lg:col-span-2">
          {it.days.map((d) => (
            <article key={d.day} className="card">
              <div className="mb-3 flex items-baseline justify-between"><h2 className="font-display text-xl">Day {d.day}{d.date ? ` · ${d.date}` : ""}</h2>
                <span className="text-xs text-muted">{d.total_hours} h · {d.areas.join(", ")}</span></div>
              <ol className="space-y-2">
                {d.items.map((i, k) => (
                  <li key={k} className={`flex justify-between gap-3 border-l-4 pl-3 ${KIND[i.kind]}`}>
                    <div><p className="text-sm font-semibold">{i.time} · {i.name}</p><p className="text-xs text-muted">{i.kind}{i.area ? ` · ${i.area}` : ""}{i.duration_hours ? ` · ${i.duration_hours} h` : ""}</p></div>
                    <span className="whitespace-nowrap text-sm">{i.kind === "travel" ? "" : i.cost ? inr(i.cost) : "Free"}</span>
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </section>

        <aside className="space-y-4">
          <section className="card">
            <h2 className="font-display text-xl">Budget breakdown</h2>
            <ul className="mt-3 space-y-2">
              {parts.map(([n, v]) => (
                <li key={n}><div className="flex justify-between text-sm"><span>{n}</span><span>{inr(v)}</span></div>
                  <div className="mt-1 h-1.5 rounded bg-line"><div className="h-1.5 rounded bg-teal" style={{ width: `${Math.min(100, (v / Math.max(c.total, 1)) * 100)}%` }} /></div></li>
              ))}
            </ul>
          </section>
          <section className="card text-sm">
            <h2 className="font-display text-xl">Stay and transport</h2>
            <p className="mt-2 font-semibold">{it.hotel.name}</p><p className="text-muted">{it.hotel.desc} · {inr(it.hotel.cost)} per room per night (estimate)</p>
            <p className="mt-3 font-semibold">{it.transport.name}</p><p className="text-muted">{it.transport.desc} · {inr(it.transport.cost)} per vehicle per day (estimate)</p>
          </section>
          <section className="card text-sm">
            <h2 className="font-display text-xl">Food picks</h2>
            <ul className="mt-2 space-y-1">{meals.map((m) => <li key={m.name} className="flex justify-between gap-2"><span>{m.name}</span><span className="text-muted">{inr(m.cost / it.travelers)} pp</span></li>)}</ul>
          </section>
          <section className="card text-sm">
            <h2 className="font-display text-xl">About {it.destination}</h2>
            <p className="mt-2 text-muted">{overview.overview}</p>
            <p className="mt-2"><b>Best season:</b> {overview.best_season}</p>
            <p className="mt-2"><b>Getting around:</b> {overview.transport_info}</p>
            <ul className="mt-2 list-disc pl-5 text-muted">{(overview.tips || []).map((t) => <li key={t}>{t}</li>)}</ul>
          </section>
        </aside>
      </div>

      <section className="card text-sm">
        <h2 className="font-display text-xl">How the agents got here</h2>
        <ul className="mt-2 space-y-1">
          {row.attempts.map((a, i) => <li key={i}>Attempt {a.attempt}: {inr(a.total)} · {a.within_budget ? "within budget" : "over budget"} · {a.approved ? "reviewer approved" : "reviewer rejected"}</li>)}
        </ul>
        {it.notes.map((n, i) => <p key={i} className="mt-2 text-muted">{n}</p>)}
        <p className="mt-2 text-muted">{overview.disclaimer}</p>
      </section>

      <section className="card space-y-4">
        <h2 className="font-display text-xl">Your decision</h2>
        <ErrorBox>{err}</ErrorBox>
        {msg && <p role="status" className="text-sm text-good">{msg}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn btn-primary" disabled={busy || running || trip.status === "approved" && trip.approved_version === viewing} onClick={act(() => approveTrip(tripId, viewing), "Approved. Preferences saved to memory.")}>
            {trip.status === "approved" && trip.approved_version === viewing ? "Approved" : "Approve itinerary"}</button>
          <button className="btn" disabled={busy || running} onClick={act(() => saveTrip(tripId), "Trip saved.")}>Save trip</button>
          <button className="btn" disabled={busy || running} onClick={revise({ regenerate: true, feedback: "" })}>Regenerate</button>
          {versions.length > 1 && (
            <label className="ml-auto flex items-center gap-2 text-sm">Version
              <select className="input w-auto" value={viewing} onChange={(e) => setVersion(Number(e.target.value))}>
                {versions.map((v) => <option key={v.version} value={v.version}>v{v.version} · {inr(v.total)} · {v.approval_status}</option>)}
              </select></label>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <input className="input flex-1" placeholder="Request changes, e.g. more food stops, skip the fort, cheaper stay" value={feedback} maxLength={1000} onChange={(e) => setFeedback(e.target.value)} aria-label="Requested changes" />
          <button className="btn" disabled={busy || running || !feedback.trim()} onClick={revise({ feedback, regenerate: false })}>Request modifications</button>
        </div>
      </section>
    </div>
  );
}
