import { useState } from "react";
import EventFilters, { EMPTY_FILTERS } from "../components/EventFilters.jsx";
import EventTable from "../components/EventTable.jsx";
import { Alert, AsyncBlock, EmptyState, ErrorAlert } from "../components/Feedback.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { api, queryString } from "../services/api.js";

const PAGE_SIZE = 25;

function LinkToCase({ selected, onDone }) {
  const cases = useApi("/cases");
  const [caseId, setCaseId] = useState("");
  const [rationale, setRationale] = useState("");
  const action = useAction();

  const link = async () => {
    const result = await action.run(
      () => api(`/cases/${caseId}/events`, { method: "POST", body: { event_ids: [...selected], rationale: rationale || undefined } }),
    );
    if (result) onDone(`${result.linked.length} event(s) linked to ${result.case.case_number}.`);
  };

  const open = cases.data?.cases.filter((c) => c.status !== "closed") ?? [];
  return (
    <div className="card" aria-label="Link selected events to case">
      <h3>Link {selected.size} selected event(s) to a case</h3>
      <ErrorAlert error={action.error || cases.error} />
      <div className="form-row">
        <div className="field">
          <label htmlFor="link-case">Case</label>
          <select id="link-case" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
            <option value="">Select a case…</option>
            {open.map((c) => <option key={c.id} value={c.id}>{c.case_number} – {c.title}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="link-rationale">Rationale (optional)</label>
          <input id="link-rationale" type="text" maxLength={300} value={rationale} onChange={(e) => setRationale(e.target.value)} />
        </div>
      </div>
      <div className="btn-row" style={{ marginTop: 12 }}>
        <button type="button" className="btn" disabled={!caseId || action.pending} onClick={link}>Link events</button>
      </div>
    </div>
  );
}

export default function AuditPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(new Set());
  const [message, setMessage] = useState(null);
  const state = useApi(`/audit/events${queryString({ ...filters, page, page_size: PAGE_SIZE })}`);
  const investigator = user.role === "investigator";

  const toggle = (id) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const title = { subject: "Access history", processor: "My access log", investigator: "Audit trail" }[user.role];
  const scope = {
    subject: "Every action you performed and every attempt by anyone to access your data.",
    processor: "Every request you made, including denied attempts.",
    investigator: "All hash-chained security and access events in the system.",
  }[user.role];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{title}</h1>
          <p>{scope} Select an event number to see its hash-chain fields.</p>
        </div>
      </div>
      <section className="card">
        <EventFilters onApply={(f) => { setFilters(f); setPage(1); }} />
      </section>
      <Alert tone="success">{message}</Alert>
      {investigator && selected.size > 0 && (
        <LinkToCase selected={selected} onDone={(msg) => { setMessage(msg); setSelected(new Set()); }} />
      )}
      <section className="card">
        <AsyncBlock state={state} isEmpty={(d) => d.total === 0}
                    empty={<EmptyState title="No matching events"><p>Adjust the filters or perform some activity.</p></EmptyState>}>
          {(d) => (
            <>
              <EventTable events={d.events} selectable={investigator} selected={selected} onToggle={toggle} />
              <div className="pager">
                <span className="small muted">
                  {d.total} event(s) · page {d.page} of {Math.max(1, Math.ceil(d.total / d.page_size))}
                </span>
                <div className="btn-row">
                  <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
                  <button type="button" className="btn btn-secondary btn-sm" disabled={page * d.page_size >= d.total} onClick={() => setPage(page + 1)}>Next</button>
                </div>
              </div>
            </>
          )}
        </AsyncBlock>
      </section>
    </>
  );
}
