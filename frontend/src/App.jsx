import { NavLink, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard.jsx";
import Assistant from "./pages/Assistant.jsx";
import Monitor from "./pages/Monitor.jsx";
import Itinerary from "./pages/Itinerary.jsx";
import Preferences from "./pages/Preferences.jsx";

const link = ({ isActive }) =>
  `rounded-lg px-3 py-1.5 text-sm font-semibold ${isActive ? "bg-teal text-paper" : "text-muted hover:text-ink"}`;

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-card/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3">
          <NavLink to="/" className="font-display text-2xl tracking-tight">TravelMate <span className="text-saffron">AI</span></NavLink>
          <nav className="flex gap-1" aria-label="Main">
            <NavLink to="/" end className={link}>Dashboard</NavLink>
            <NavLink to="/plan" className={link}>Plan a trip</NavLink>
            <NavLink to="/preferences" className={link}>Preferences</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/plan" element={<Assistant />} />
          <Route path="/trips/:tripId" element={<Itinerary />} />
          <Route path="/trips/:tripId/activity/:executionId" element={<Monitor />} />
          <Route path="/preferences" element={<Preferences />} />
          <Route path="*" element={<p className="text-muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
