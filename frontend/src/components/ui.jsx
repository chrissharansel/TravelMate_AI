const STATUS = {
  approved: "bg-good/15 text-good", saved: "bg-teal/15 text-teal", awaiting_approval: "bg-saffron/15 text-saffron",
  planning: "bg-teal/15 text-teal", revising: "bg-teal/15 text-teal", failed: "bg-bad/15 text-bad", needs_info: "bg-bad/15 text-bad",
};
const LABEL = { awaiting_approval: "awaiting approval", needs_info: "needs info" };

export const StatusBadge = ({ status }) => (
  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS[status] || "bg-line text-muted"}`}>{LABEL[status] || status}</span>
);

export const Spinner = ({ label = "Loading" }) => (
  <div role="status" className="flex items-center gap-2 text-sm text-muted">
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-teal" /> {label}
  </div>
);

export const ErrorBox = ({ children }) =>
  children ? <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">{children}</p> : null;

export const PageTitle = ({ title, sub, children }) => (
  <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 className="font-display text-3xl tracking-tight">{title}</h1>
      {sub && <p className="mt-1 text-muted">{sub}</p>}
    </div>
    {children}
  </div>
);
