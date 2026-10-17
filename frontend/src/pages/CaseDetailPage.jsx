import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { OutcomeBadge, StatusBadge } from "../components/Badge.jsx";
import EventFilters, { EMPTY_FILTERS } from "../components/EventFilters.jsx";
import EventTable from "../components/EventTable.jsx";
import { Alert, AsyncBlock, EmptyState, ErrorAlert } from "../components/Feedback.jsx";
import IndicatorList from "../components/IndicatorList.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { api, downloadFile, queryString } from "../services/api.js";
import { formatTimestamp, humanize, personLabel } from "../utils/format.js";

const TABS = [
  ["timeline", "Timeline"],
  ["evidence", "Evidence"],
  ["indicators", "Indicators"],
  ["notes", "Notes & findings"],
  ["report", "Report"],
];
const NEXT_STATUS = { open: ["under_review", "closed"], under_review: ["open", "closed"], closed: ["under_review"] };

function TimelineTab({ caseId }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const state = useApi(`/cases/${caseId}/timeline${queryString(filters)}`);
  return (
    <>
      <details className="card">
        <summary><strong>Filter timeline</strong></summary>
        <div style={{ marginTop: 12 }}><EventFilters onApply={setFilters} /></div>
      </details>
      <div className="legend-row" style={{ marginBottom: 12 }}>
        <span>● Observed audit events (green allowed / red denied)</span>
        <span>● Consent history (blue)</span>
      </div>
      <AsyncBlock state={state} isEmpty={(d) => d.timeline.length === 0}
                  empty={<EmptyState title="Timeline is empty"><p>Link evidence events from the audit trail or detection page.</p></EmptyState>}>
        {(d) => (
          <ul className="timeline">
            {d.timeline.map((item, i) =>
              item.source === "audit_event" ? (
                <li key={item.event.event_id}>
                  <span className={`dot ${item.event.outcome}`} />
                  <div className="when">{formatTimestamp(item.timestamp)} · #{item.seq}</div>
                  <div className="what">
                    <code>{item.event.event_type}</code> <OutcomeBadge outcome={item.event.outcome} />{" "}
                    {item.event.reason_code && <span className="small">{item.event.reason_code}</span>}
                  </div>
                  <div className="small muted">
                    Actor: {personLabel(item.event.actor, item.event.actor_id)} · Resource: {item.event.resource_type}{" "}
                    {item.event.resource_id} {item.event.consent_id ? `· Consent #${item.event.consent_id}` : ""}
                    {item.event.details?.purpose ? ` · purpose ${item.event.details.purpose}` : ""}
                  </div>
                  <div className="hash">{item.event.event_id}</div>
                </li>
              ) : (
                <li key={`c-${item.consent_id}-${item.version.version}-${i}`}>
                  <span className="dot consent" />
                  <div className="when">{formatTimestamp(item.timestamp)}</div>
                  <div className="what">
                    Consent #{item.consent_id} {humanize(item.version.change_type)} (v{item.version.version}){" "}
                    <StatusBadge status={item.version.status} />
                  </div>
                  <div className="small muted">
                    Purpose {item.consent.purpose} · categories {item.version.categories.join(", ")} · subject #
                    {item.consent.subject_id} → recipient #{item.consent.recipient_id}
                  </div>
                </li>
              ),
            )}
          </ul>
        )}
      </AsyncBlock>
    </>
  );
}

function EvidenceTab({ caseId, onChange }) {
  const state = useApi(`/cases/${caseId}/events`);
  const action = useAction();
  const unlink = async (eventId) => {
    if (!window.confirm("Remove this event from the case? The removal is recorded in the audit trail.")) return;
    const result = await action.run(() => api(`/cases/${caseId}/events/${eventId}`, { method: "DELETE" }));
    if (result) { state.reload(); onChange(); }
  };
  return (
    <>
      <p className="muted small">
        Evidence items are audit events linked to this case. Add more from the <Link to="/audit">audit trail</Link> or{" "}
        <Link to="/detection">detection rules</Link>.
      </p>
      <ErrorAlert error={action.error} />
      <AsyncBlock state={state} isEmpty={(d) => d.events.length === 0}
                  empty={<EmptyState title="No evidence linked"><p>Select events in the audit trail and link them to this case.</p></EmptyState>}>
        {(d) => (
          <EventTable events={d.events} actions={(e) => (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => unlink(e.event_id)}>Unlink</button>
          )} />
        )}
      </AsyncBlock>
    </>
  );
}

function IndicatorsTab({ caseId }) {
  const [th, setTh] = useState({ window_minutes: "", denial_threshold: "", probing_threshold: "", failed_login_threshold: "" });
  const [applied, setApplied] = useState({});
  const state = useApi(`/cases/${caseId}/indicators${queryString(applied)}`);
  return (
    <>
      <form className="card form" onSubmit={(e) => { e.preventDefault(); setApplied(th); }}>
        <strong>Rule thresholds</strong>
        <div className="form-row">
          {[["window_minutes", "Window (minutes)"], ["denial_threshold", "Denials (R1)"], ["probing_threshold", "Distinct resources (R6)"],
            ["failed_login_threshold", "Failed logins (R7)"]].map(([key, label]) => (
            <div className="field" key={key}>
              <label htmlFor={`th-${key}`}>{label}</label>
              <input id={`th-${key}`} type="number" min="1" placeholder={state.data ? String(state.data.thresholds[key]) : ""}
                     value={th[key]} onChange={(e) => setTh({ ...th, [key]: e.target.value })} />
            </div>
          ))}
        </div>
        <div><button className="btn btn-secondary" type="submit">Re-evaluate</button></div>
      </form>
      <AsyncBlock state={state}>{(d) => <IndicatorList indicators={d.indicators} />}</AsyncBlock>
    </>
  );
}

function NotesTab({ caseId, notes, onAdded }) {
  const [form, setForm] = useState({ note_type: "note", content: "" });
  const action = useAction();
  const submit = async (e) => {
    e.preventDefault();
    const result = await action.run(() => api(`/cases/${caseId}/notes`, { method: "POST", body: form }), "Note recorded.");
    if (result) { setForm({ note_type: form.note_type, content: "" }); onAdded(); }
  };
  return (
    <div className="grid grid-2">
      <section>
        <h3>Add entry</h3>
        <p className="small muted">
          Notes are append-only. Use <em>finding</em> for interpretations of evidence and <em>conclusion</em> only for
          final investigator conclusions.
        </p>
        <Alert tone="success">{action.success}</Alert>
        <ErrorAlert error={action.error} />
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="note-type">Entry type</label>
            <select id="note-type" value={form.note_type} onChange={(e) => setForm({ ...form, note_type: e.target.value })}>
              <option value="note">Note</option>
              <option value="finding">Finding</option>
              <option value="conclusion">Conclusion</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="note-content">Content</label>
            <textarea id="note-content" required maxLength={5000} value={form.content}
                      onChange={(e) => setForm({ ...form, content: e.target.value })} />
          </div>
          <div><button className="btn" type="submit" disabled={action.pending}>Save entry</button></div>
        </form>
      </section>
      <section>
        <h3>Recorded entries</h3>
        {notes.length === 0 ? <EmptyState title="No entries yet" /> : notes.map((n) => (
          <article key={n.id} className={`note ${n.note_type}`}>
            <div className="small muted">
              <strong>{humanize(n.note_type)}</strong> · {personLabel(n.author)} · {formatTimestamp(n.created_at)}
            </div>
            <pre>{n.content}</pre>
          </article>
        ))}
      </section>
    </div>
  );
}

function ReportTab({ caseData }) {
  const action = useAction();
  const download = () =>
    action.run(() => downloadFile(`/cases/${caseData.id}/report.pdf`, `${caseData.case_number}-report.pdf`), "Report generated and downloaded.");
  return (
    <div>
      <p>The PDF report contains, in clearly separated sections:</p>
      <ol>
        <li>Case overview, scope and method</li>
        <li>Observed facts: event summary, chronological timeline with event IDs, consent records and history</li>
        <li>System-generated indicators with triggering rules and supporting event IDs</li>
        <li>Audit-integrity verification result and chain head hash</li>
        <li>Investigator notes and findings, followed by conclusions</li>
        <li>Limitations</li>
      </ol>
      <p className="small muted">Report generation is authorized on the server and recorded in the audit trail. No plaintext record content is included.</p>
      <Alert tone="success">{action.success}</Alert>
      <ErrorAlert error={action.error} />
      <button type="button" className="btn" onClick={download} disabled={action.pending}>
        {action.pending ? "Generating…" : "Download PDF report"}
      </button>
    </div>
  );
}

export default function CaseDetailPage() {
  const { id } = useParams();
  const state = useApi(`/cases/${id}`);
  const [tab, setTab] = useState("timeline");
  const [statusForm, setStatusForm] = useState({ status: "", note: "" });
  const action = useAction();

  const changeStatus = async (e) => {
    e.preventDefault();
    const body = { status: statusForm.status };
    if (statusForm.note) body.status_note = statusForm.note;
    const result = await action.run(() => api(`/cases/${id}`, { method: "PATCH", body }), "Case status updated.");
    if (result) { setStatusForm({ status: "", note: "" }); state.reload(); }
  };

  return (
    <AsyncBlock state={state}>
      {({ case: c, notes }) => (
        <>
          <div className="page-header">
            <div>
              <p className="small"><Link to="/cases">← All cases</Link></p>
              <h1>{c.case_number}: {c.title}</h1>
              <p>Lead investigator {personLabel(c.investigator)} · opened {formatTimestamp(c.created_at)}</p>
            </div>
            <StatusBadge status={c.status} />
          </div>
          <div className="grid grid-2">
            <section className="card">
              <h2>Case summary</h2>
              <dl className="dl">
                <dt>Description</dt><dd>{c.description || "—"}</dd>
                <dt>Scope</dt><dd>{c.scope_start ? formatTimestamp(c.scope_start) : "open"} → {c.scope_end ? formatTimestamp(c.scope_end) : "open"}</dd>
                <dt>Evidence items</dt><dd>{c.linked_event_count}</dd>
                <dt>Notes</dt><dd>{c.note_count}</dd>
                <dt>Last updated</dt><dd>{formatTimestamp(c.updated_at)}</dd>
                {c.closed_at && (<><dt>Closed</dt><dd>{formatTimestamp(c.closed_at)}</dd></>)}
              </dl>
            </section>
            <section className="card">
              <h2>Change status</h2>
              <Alert tone="success">{action.success}</Alert>
              <ErrorAlert error={action.error} />
              <form className="form" onSubmit={changeStatus}>
                <div className="field">
                  <label htmlFor="case-status">New status</label>
                  <select id="case-status" required value={statusForm.status} onChange={(e) => setStatusForm({ ...statusForm, status: e.target.value })}>
                    <option value="">Select…</option>
                    {NEXT_STATUS[c.status].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="case-status-note">Justification {c.status === "closed" ? "(required to re-open)" : "(optional)"}</label>
                  <textarea id="case-status-note" maxLength={2000} required={c.status === "closed"} value={statusForm.note}
                            onChange={(e) => setStatusForm({ ...statusForm, note: e.target.value })} />
                </div>
                <div><button className="btn btn-secondary" type="submit" disabled={action.pending}>Update status</button></div>
              </form>
            </section>
          </div>
          <section className="card">
            <div className="tabs" role="tablist" aria-label="Case sections">
              {TABS.map(([key, label]) => (
                <button key={key} type="button" role="tab" id={`tab-${key}`} aria-controls={`panel-${key}`}
                        aria-selected={tab === key} className="tab" onClick={() => setTab(key)}>{label}</button>
              ))}
            </div>
            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
              {tab === "timeline" && <TimelineTab caseId={id} />}
              {tab === "evidence" && <EvidenceTab caseId={id} onChange={state.reload} />}
              {tab === "indicators" && <IndicatorsTab caseId={id} />}
              {tab === "notes" && <NotesTab caseId={id} notes={notes} onAdded={state.reload} />}
              {tab === "report" && <ReportTab caseData={c} />}
            </div>
          </section>
        </>
      )}
    </AsyncBlock>
  );
}
