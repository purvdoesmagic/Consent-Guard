import { useState } from "react";
import { Alert, AsyncBlock, ErrorAlert } from "../components/Feedback.jsx";
import IndicatorList from "../components/IndicatorList.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { api, queryString } from "../services/api.js";
import { toIsoFromLocalInput } from "../utils/format.js";

const RULES = [
  ["R1", "Repeated denials", "≥ N denied record-access attempts by one actor within W minutes."],
  ["R2", "Access after withdrawal", "Any attempt denied because the covering consent was withdrawn."],
  ["R3", "Access after expiry", "Any attempt denied because the covering consent had expired."],
  ["R4", "Purpose mismatch", "Access requested for a purpose the subject did not consent to."],
  ["R5", "Category mismatch", "Access requested to a data category not covered by consent."],
  ["R6", "Broad probing", "One actor denied on ≥ M distinct resources without ownership or consent within W minutes."],
  ["R7", "Failed authentication burst", "≥ K failed login/MFA attempts against one account within W minutes."],
];

function LinkIndicator({ indicator, cases, onLinked }) {
  const [caseId, setCaseId] = useState("");
  const action = useAction();
  const link = async () => {
    const result = await action.run(() =>
      api(`/cases/${caseId}/events`, {
        method: "POST",
        body: { event_ids: indicator.event_ids, rationale: `Supporting events for ${indicator.rule_id} ${indicator.rule_code}` },
      }),
    );
    if (result) onLinked(`${result.linked.length} event(s) linked to ${result.case.case_number}.`);
  };
  return (
    <div className="btn-row">
      <label className="visually-hidden" htmlFor={`link-${indicator.rule_id}-${indicator.first_seen}`}>Case</label>
      <select id={`link-${indicator.rule_id}-${indicator.first_seen}`} value={caseId} onChange={(e) => setCaseId(e.target.value)}
              style={{ maxWidth: 280 }}>
        <option value="">Link supporting events to case…</option>
        {cases.map((c) => <option key={c.id} value={c.id}>{c.case_number} – {c.title}</option>)}
      </select>
      <button type="button" className="btn btn-secondary btn-sm" disabled={!caseId || action.pending} onClick={link}>Link</button>
      {action.error && <span className="small" role="alert">{action.error.message}</span>}
    </div>
  );
}

export default function DetectionPage() {
  const [form, setForm] = useState({ start: "", end: "", window_minutes: "", denial_threshold: "", probing_threshold: "", failed_login_threshold: "" });
  const [params, setParams] = useState({});
  const [message, setMessage] = useState(null);
  const state = useApi(`/detection/indicators${queryString(params)}`);
  const cases = useApi("/cases");
  const openCases = cases.data?.cases.filter((c) => c.status !== "closed") ?? [];
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const run = (e) => {
    e.preventDefault();
    setParams({ ...form, start: toIsoFromLocalInput(form.start) ?? "", end: toIsoFromLocalInput(form.end) ?? "" });
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Detection rules</h1>
          <p>Run the documented rules across all audit events to find leads, then link the supporting events to a case.</p>
        </div>
      </div>
      <div className="grid grid-2">
        <section className="card">
          <h2>Parameters</h2>
          <form className="form" onSubmit={run}>
            <div className="form-row">
              <div className="field"><label htmlFor="d-start">From (local time)</label><input id="d-start" type="datetime-local" value={form.start} onChange={set("start")} /></div>
              <div className="field"><label htmlFor="d-end">To (local time)</label><input id="d-end" type="datetime-local" value={form.end} onChange={set("end")} /></div>
            </div>
            <div className="form-row">
              <div className="field"><label htmlFor="d-w">Window W (min)</label><input id="d-w" type="number" min="1" placeholder={String(state.data?.thresholds.window_minutes ?? "")} value={form.window_minutes} onChange={set("window_minutes")} /></div>
              <div className="field"><label htmlFor="d-n">N denials</label><input id="d-n" type="number" min="2" placeholder={String(state.data?.thresholds.denial_threshold ?? "")} value={form.denial_threshold} onChange={set("denial_threshold")} /></div>
              <div className="field"><label htmlFor="d-m">M resources</label><input id="d-m" type="number" min="2" placeholder={String(state.data?.thresholds.probing_threshold ?? "")} value={form.probing_threshold} onChange={set("probing_threshold")} /></div>
              <div className="field"><label htmlFor="d-k">K failed logins</label><input id="d-k" type="number" min="2" placeholder={String(state.data?.thresholds.failed_login_threshold ?? "")} value={form.failed_login_threshold} onChange={set("failed_login_threshold")} /></div>
            </div>
            <div><button className="btn" type="submit">Run rules</button></div>
          </form>
        </section>
        <section className="card">
          <h2>Rule catalogue</h2>
          <div className="table-wrap">
            <table>
              <tbody>
                {RULES.map(([id, name, desc]) => (
                  <tr key={id}><td><code>{id}</code></td><td><strong>{name}</strong><div className="small muted">{desc}</div></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <Alert tone="success">{message}</Alert>
      <ErrorAlert error={cases.error} />
      <section className="card">
        <AsyncBlock state={state}>
          {(d) => (
            <>
              <p className="small muted">{d.events_examined} event(s) examined.</p>
              <IndicatorList
                indicators={d.indicators}
                renderActions={(ind) => <LinkIndicator indicator={ind} cases={openCases} onLinked={setMessage} />}
              />
            </>
          )}
        </AsyncBlock>
      </section>
    </>
  );
}
