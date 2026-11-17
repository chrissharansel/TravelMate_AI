import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getPreferences, inr, listTrips, errText } from "../api";
import { ErrorBox, PageTitle, Spinner, StatusBadge } from "../components/ui.jsx";

function TripRow({ t }) {
  const running = t.status === "planning" || t.status === "revising";
  const to = running ? `/trips/${t.trip_id}/activity/${t.latest_execution_id}` : `/trips/${t.trip_id}`;
  return (
    <Link to={to} className="flex items-center justify-between gap-3 rounded-lg border border-line px-4 py-3 hover:border-teal">
      <div>
        <p className="font-semibold">{t.destination}{t.duration ? ` · ${t.duration} days` : ""}</p>
        <p className="text-sm text-muted">{t.total_budget ? `Budget ${inr(t.total_budget)}` : "Budget not set"} · {t.travelers} traveler(s)</p>
      </div>
      <StatusBadge status={t.status} />
    </Link>
  );
}

export default function Dashboard() {
  const [trips, setTrips] = useState(null);
  const [prefs, setPrefs] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([listTrips(), getPreferences()]).then(([t, p]) => { setTrips(t); setPrefs(p); }).catch((e) => setErr(errText(e)));
  }, []);

  if (err) return <ErrorBox>{err}. Is the backend running on port 8000 and MongoDB reachable?</ErrorBox>;
  if (!trips) return <Spinner />;

  const saved = trips.filter((t) => t.status === "approved" || t.status === "saved");
  const confirmed = (prefs?.memory || []).filter((m) => m.source === "confirmed");
  const p = prefs?.preferences || {};

  return (
    <div className="fade space-y-8">
      <section className="card flex flex-wrap items-center justify-between gap-4 bg-teal/10">
        <div>
          <h1 className="font-display text-4xl tracking-tight">Where to next?</h1>
          <p className="mt-1 max-w-xl text-muted">Describe a trip in plain words. Four agents research, price, review and revise it until it fits your budget, then you decide.</p>
        </div>
        <Link to="/plan" className="btn btn-primary">Create new trip</Link>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <PageTitle title="Previous trips" />
          <div className="space-y-2">
            {trips.length === 0 && <p className="text-muted">No trips yet. Plan your first one.</p>}
            {trips.map((t) => <TripRow key={t.trip_id} t={t} />)}
          </div>
        </section>

        <aside className="space-y-6">
          <section>
            <PageTitle title="Saved itineraries" />
            <div className="space-y-2">
              {saved.length === 0 && <p className="text-sm text-muted">Approved or saved trips show up here.</p>}
              {saved.map((t) => <TripRow key={t.trip_id} t={t} />)}
            </div>
          </section>
          <section className="card">
            <h2 className="font-display text-xl">Your preferences</h2>
            <dl className="mt-3 space-y-1 text-sm">
              <div><dt className="inline text-muted">Activities: </dt><dd className="inline">{(p.preferred_activities || []).join(", ") || "-"}</dd></div>
              <div><dt className="inline text-muted">Food: </dt><dd className="inline">{(p.food_preferences || []).join(", ") || "-"}</dd></div>
              <div><dt className="inline text-muted">Stay: </dt><dd className="inline">{(p.accommodation_preferences || []).join(", ") || "-"}</dd></div>
              <div><dt className="inline text-muted">Remembered (confirmed): </dt><dd className="inline">{confirmed.map((m) => m.value).join(", ") || "-"}</dd></div>
            </dl>
            <Link to="/preferences" className="mt-3 inline-block text-sm font-semibold text-teal underline">Manage preferences</Link>
          </section>
        </aside>
      </div>
    </div>
  );
}
