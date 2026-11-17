import { useEffect, useState } from "react";
import { confirmMemory, deleteMemory, errText, getPreferences, putPreferences } from "../api";
import { ErrorBox, PageTitle, Spinner } from "../components/ui.jsx";

const FIELDS = [
  ["preferred_destinations", "Preferred destinations", "goa, kerala"],
  ["preferred_activities", "Preferred activities", "beach, sightseeing, food"],
  ["food_preferences", "Food preferences", "vegetarian, seafood"],
  ["accommodation_preferences", "Accommodation preferences", "budget, homestay"],
];
const toList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Preferences() {
  const [form, setForm] = useState(null);
  const [memory, setMemory] = useState([]);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState(false);

  const apply = (d) => {
    const p = d.preferences || {};
    setForm({ ...Object.fromEntries(FIELDS.map(([k]) => [k, (p[k] || []).join(", ")])), travel_style: p.travel_style || "", budget_preference: p.budget_preference || "" });
    setMemory(d.memory || []);
  };
  useEffect(() => { getPreferences().then(apply).catch((e) => setErr(errText(e))); }, []);

  async function save(e) {
    e.preventDefault(); setErr(""); setSaved(false);
    try {
      const body = Object.fromEntries(FIELDS.map(([k]) => [k, toList(form[k])]));
      body.travel_style = form.travel_style || null; body.budget_preference = form.budget_preference || null;
      apply(await putPreferences(body)); setSaved(true);
    } catch (e2) { setErr(errText(e2)); }
  }
  const refresh = () => getPreferences().then(apply).catch((e) => setErr(errText(e)));

  if (!form) return err ? <ErrorBox>{err}</ErrorBox> : <Spinner />;
  return (
    <div className="fade grid gap-6 lg:grid-cols-2">
      <form onSubmit={save} className="card space-y-4">
        <PageTitle title="Travel preferences" sub="What you save here is treated as confirmed and used in every plan." />
        {FIELDS.map(([k, label, ph]) => (
          <div key={k}><label htmlFor={k} className="text-sm font-semibold">{label}</label>
            <input id={k} className="input" placeholder={ph} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></div>
        ))}
        <div className="grid gap-4 sm:grid-cols-2">
          <div><label htmlFor="ts" className="text-sm font-semibold">Travel style</label>
            <select id="ts" className="input" value={form.travel_style} onChange={(e) => setForm({ ...form, travel_style: e.target.value })}>
              <option value="">No preference</option><option>relaxed</option><option>balanced</option><option>packed</option><option>adventurous</option></select></div>
          <div><label htmlFor="bp" className="text-sm font-semibold">Budget preference</label>
            <select id="bp" className="input" value={form.budget_preference} onChange={(e) => setForm({ ...form, budget_preference: e.target.value })}>
              <option value="">No preference</option><option>budget</option><option>mid-range</option><option>comfort</option></select></div>
        </div>
        <ErrorBox>{err}</ErrorBox>
        {saved && <p role="status" className="text-sm text-good">Preferences saved.</p>}
        <button className="btn btn-primary">Save preferences</button>
      </form>

      <section className="card">
        <h2 className="font-display text-xl">What the system remembers</h2>
        <p className="mt-1 text-sm text-muted">Confirmed means you stated or approved it. Assumed means the AI guessed; it is only a soft hint until you confirm it.</p>
        <ul className="mt-4 space-y-2">
          {memory.length === 0 && <li className="text-sm text-muted">Nothing yet. Approve a trip to build memory.</li>}
          {memory.map((m) => (
            <li key={m.key} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
              <span><b>{m.kind}</b>: {m.value} <span className={`ml-1 rounded-full px-2 py-0.5 text-xs font-semibold ${m.source === "confirmed" ? "bg-good/15 text-good" : "bg-saffron/15 text-saffron"}`}>{m.source}</span></span>
              <span className="flex gap-2">
                {m.source !== "confirmed" && <button className="btn px-2 py-1" onClick={() => confirmMemory(m.key).then(refresh)}>Confirm</button>}
                <button className="btn px-2 py-1" onClick={() => deleteMemory(m.key).then(refresh)} aria-label={`Remove ${m.value}`}>Remove</button>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
