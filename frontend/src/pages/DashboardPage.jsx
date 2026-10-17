import { Link } from "react-router-dom";
import EventTable from "../components/EventTable.jsx";
import { AsyncBlock, EmptyState } from "../components/Feedback.jsx";
import { useApi } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { formatTimestamp } from "../utils/format.js";

const INTRO = {
  subject: "Overview of the consents you have granted and every attempt to access your protected data.",
  processor: "Overview of consents granted to you and your data-access requests.",
  investigator: "System-wide privacy accountability overview for investigations.",
};

function Stat({ label, value, hint, tone }) {
  return (
    <div className={`stat${tone ? ` ${tone}` : ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const state = useApi("/dashboard");

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Welcome, {user.display_name}</h1>
          <p>{INTRO[user.role]}</p>
        </div>
        <button className="btn btn-secondary" type="button" onClick={state.reload} disabled={state.loading}>
          Refresh
        </button>
      </div>
      <AsyncBlock state={state} loadingLabel="Loading dashboard…">
        {(d) => (
          <>
            <section className="stats" aria-label="Key statistics">
              <Stat label="Active consents" value={d.consents.active} tone="ok" />
              <Stat label="Withdrawn consents" value={d.consents.withdrawn} />
              <Stat label="Expired consents" value={d.consents.expired} />
              <Stat label="Access attempts" value={d.access.total}
                    hint={user.role === "subject" ? "on your records" : user.role === "processor" ? "made by you" : "all records"} />
              <Stat label="Denied attempts" value={d.access.denied} tone={d.access.denied ? "bad" : undefined} />
              {d.open_cases !== null && <Stat label="Open cases" value={d.open_cases} hint="assigned to you" />}
              <Stat
                label="Audit integrity"
                value={d.integrity.valid ? "Valid" : "Invalid"}
                tone={d.integrity.valid ? "ok" : "bad"}
                hint={`${d.integrity.event_count} events · checked ${formatTimestamp(d.integrity.checked_at)}`}
              />
            </section>
            {!d.integrity.valid && (
              <div className="alert alert-error" role="alert">
                The audit chain failed verification with {d.integrity.finding_count} finding(s).{" "}
                <Link to="/integrity">View integrity details</Link>
              </div>
            )}
            <section className="card">
              <div className="card-header">
                <h2>Recent activity</h2>
                <Link to="/audit">View full history</Link>
              </div>
              {d.recent_events.length ? (
                <EventTable events={d.recent_events} />
              ) : (
                <EmptyState title="No activity yet">
                  <p>Events appear here as consents change and data is accessed.</p>
                </EmptyState>
              )}
            </section>
          </>
        )}
      </AsyncBlock>
    </>
  );
}
