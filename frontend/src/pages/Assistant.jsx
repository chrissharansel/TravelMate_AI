import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errText, planTrip } from "../api";
import { ErrorBox, PageTitle } from "../components/ui.jsx";

const DESTINATIONS = ["Goa", "Kerala", "Ooty", "Coorg", "Manali", "Jaipur", "Pondicherry", "Chennai"];
const INTERESTS = ["beach", "sightseeing", "food", "adventure", "nature", "heritage", "shopping", "relax", "culture", "nightlife"];
const EXAMPLE = "Plan a 3-day Goa trip for two people within ₹15,000. I like beaches, sightseeing and good food.";

export default function Assistant() {
  const nav = useNavigate();
  const [message, setMessage] = useState(EXAMPLE);
  const [f, setF] = useState({ destination: "", budget: "", days: "", travelers: "", start_date: "", interests: [] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggle = (i) => setF({ ...f, interests: f.interests.includes(i) ? f.interests.filter((x) => x !== i) : [...f.interests, i] });

  async function submit(e) {
    e.preventDefault();
    setErr(""); setBusy(true);
    const body = { message };
    if (f.destination) body.destination = f.destination;
    if (f.budget) body.budget = Number(f.budget);
    if (f.days) body.days = Number(f.days);
    if (f.travelers) body.travelers = Number(f.travelers);
    if (f.start_date) body.start_date = f.start_date;
    if (f.interests.length) body.interests = f.interests;
    try {
      const r = await planTrip(body);
      nav(`/trips/${r.trip_id}/activity/${r.execution_id}`);
    } catch (e2) { setErr(errText(e2)); setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="fade mx-auto max-w-3xl space-y-6">
      <PageTitle title="Travel assistant" sub="Write it naturally, fill the fields, or both. Fields override what the text says." />
      <div className="card space-y-3">
        <label htmlFor="msg" className="text-sm font-semibold">Your trip in your own words</label>
        <textarea id="msg" className="input" rows={4} value={message} maxLength={2000} onChange={(e) => setMessage(e.target.value)} />
      </div>

      <div className="card grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="dest" className="text-sm font-semibold">Destination</label>
          <select id="dest" className="input" value={f.destination} onChange={set("destination")}>
            <option value="">Detect from text</option>
            {DESTINATIONS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="bud" className="text-sm font-semibold">Total budget (₹)</label>
          <input id="bud" className="input" type="number" min="1" step="500" placeholder="15000" value={f.budget} onChange={set("budget")} />
        </div>
        <div>
          <label htmlFor="days" className="text-sm font-semibold">Number of days</label>
          <input id="days" className="input" type="number" min="1" max="14" placeholder="3" value={f.days} onChange={set("days")} />
        </div>
        <div>
          <label htmlFor="trav" className="text-sm font-semibold">Travelers</label>
          <input id="trav" className="input" type="number" min="1" max="12" placeholder="2" value={f.travelers} onChange={set("travelers")} />
        </div>
        <div>
          <label htmlFor="sd" className="text-sm font-semibold">Start date (optional)</label>
          <input id="sd" className="input" type="date" value={f.start_date} onChange={set("start_date")} />
        </div>
        <fieldset className="sm:col-span-2">
          <legend className="text-sm font-semibold">Interests</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {INTERESTS.map((i) => (
              <button type="button" key={i} aria-pressed={f.interests.includes(i)} onClick={() => toggle(i)}
                className={`rounded-full border px-3 py-1 text-sm ${f.interests.includes(i) ? "border-teal bg-teal text-paper" : "border-line text-muted hover:border-teal"}`}>{i}</button>
            ))}
          </div>
        </fieldset>
      </div>

      <ErrorBox>{err}</ErrorBox>
      <button className="btn btn-primary" disabled={busy || (!message.trim() && !f.destination)}>{busy ? "Starting the agents…" : "Plan my trip"}</button>
    </form>
  );
}
