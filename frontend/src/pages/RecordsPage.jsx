import { useState } from "react";
import { Badge } from "../components/Badge.jsx";
import { Alert, AsyncBlock, EmptyState, ErrorAlert } from "../components/Feedback.jsx";
import PayloadView from "../components/PayloadView.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { api } from "../services/api.js";
import { formatTimestamp, humanize, personLabel, REASON_TEXT } from "../utils/format.js";

const SAMPLE_FIELDS = {
  health: [["Test", "Synthetic lipid panel"], ["Result", "Within fictional range"], ["Notice", "SYNTHETIC DEMO DATA"]],
  contact: [["Address", "42 Imaginary Lane, Testville"], ["Phone", "+00 000 0000"], ["Notice", "SYNTHETIC DEMO DATA"]],
  financial: [["Account", "XX-0000 (fictional)"], ["Balance band", "1,000-5,000"], ["Notice", "SYNTHETIC DEMO DATA"]],
  location: [["City", "Sampletown"], ["Last check-in", "Fictional Plaza"], ["Notice", "SYNTHETIC DEMO DATA"]],
  demographic: [["Age band", "30-39"], ["Region", "Nowhere County"], ["Notice", "SYNTHETIC DEMO DATA"]],
};

function AccessResult({ result }) {
  if (!result) return null;
  if (result.error) {
    const reason = result.error.details?.reason ?? result.error.code;
    return (
      <div className="alert alert-error" role="alert">
        <strong>{REASON_TEXT[reason] ?? result.error.message}</strong>
        <span className="ref">Code: {reason} · Reference: {result.error.requestId}</span>
        <span className="ref">This attempt has been recorded in the audit trail.</span>
      </div>
    );
  }
  return (
    <div>
      <Alert tone="success">
        <strong>{REASON_TEXT[result.decision] ?? result.decision}</strong>
        {result.consent_id && <span> (consent #{result.consent_id})</span>}
        <span className="ref">Decrypted server-side after authorization; this access has been logged.</span>
      </Alert>
      <PayloadView payload={result.payload} />
    </div>
  );
}

function CreateRecordForm({ categories, onCreated }) {
  const [form, setForm] = useState({ label: "", category: "", fields: [["", ""]] });
  const action = useAction();

  const setField = (i, j, value) =>
    setForm((f) => ({ ...f, fields: f.fields.map((row, k) => (k === i ? (j === 0 ? [value, row[1]] : [row[0], value]) : row)) }));

  const fillSample = () => {
    const category = form.category || "health";
    setForm({ label: `Synthetic ${humanize(category).toLowerCase()} record`, category, fields: SAMPLE_FIELDS[category] });
  };

  const submit = async (e) => {
    e.preventDefault();
    const fields = Object.fromEntries(form.fields.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), v]));
    const result = await action.run(
      () => api("/records", { method: "POST", body: { label: form.label, category: form.category, fields } }),
      "Record encrypted and stored.",
    );
    if (result) {
      setForm({ label: "", category: "", fields: [["", ""]] });
      onCreated();
    }
  };

  return (
    <form className="form" onSubmit={submit}>
      <Alert tone="warning">Enter synthetic values only. Never store real personal data in this demonstration.</Alert>
      <Alert tone="success">{action.success}</Alert>
      <ErrorAlert error={action.error} />
      <div className="form-row">
        <div className="field">
          <label htmlFor="rec-label">Label (non-sensitive metadata)</label>
          <input id="rec-label" type="text" required minLength={3} maxLength={120} value={form.label}
                 onChange={(e) => setForm({ ...form, label: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="rec-category">Data category</label>
          <select id="rec-category" required value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">Select…</option>
            {categories.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
          </select>
        </div>
      </div>
      <fieldset>
        <legend>Encrypted fields</legend>
        <div className="form">
          {form.fields.map(([key, value], i) => (
            <div className="form-row" key={i}>
              <div className="field">
                <label htmlFor={`fk-${i}`}>Field name</label>
                <input id={`fk-${i}`} type="text" maxLength={40} value={key} onChange={(e) => setField(i, 0, e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor={`fv-${i}`}>Value</label>
                <input id={`fv-${i}`} type="text" maxLength={500} value={value} onChange={(e) => setField(i, 1, e.target.value)} />
              </div>
            </div>
          ))}
          <div className="btn-row">
            <button type="button" className="btn btn-secondary btn-sm" disabled={form.fields.length >= 12}
                    onClick={() => setForm({ ...form, fields: [...form.fields, ["", ""]] })}>Add field</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={fillSample}>Fill synthetic example</button>
          </div>
        </div>
      </fieldset>
      <div><button className="btn" type="submit" disabled={action.pending}>Encrypt &amp; store</button></div>
    </form>
  );
}

function SubjectRecords({ meta }) {
  const state = useApi("/records");
  const [results, setResults] = useState({});
  const [showForm, setShowForm] = useState(false);

  const view = async (record, action = "read") => {
    try {
      const result = await api(`/records/${record.id}/access`, { method: "POST", body: { action } });
      setResults((r) => ({ ...r, [record.id]: result }));
    } catch (error) {
      setResults((r) => ({ ...r, [record.id]: { error } }));
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>My protected records</h1>
          <p>Synthetic records encrypted with AES-256-GCM. Only metadata is stored in clear text.</p>
        </div>
        <button className="btn" type="button" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Close form" : "Add synthetic record"}
        </button>
      </div>
      {showForm && meta && (
        <section className="card">
          <h2>New synthetic record</h2>
          <CreateRecordForm categories={meta.categories} onCreated={state.reload} />
        </section>
      )}
      <section className="card">
        <AsyncBlock state={state} isEmpty={(d) => d.records.length === 0}
                    empty={<EmptyState title="No records yet"><p>Add a synthetic record to get started.</p></EmptyState>}>
          {(d) => d.records.map((r) => (
            <article key={r.id} className="note">
              <div className="card-header" style={{ marginBottom: 6 }}>
                <div>
                  <h3>{r.label}</h3>
                  <div className="small muted">
                    <Badge tone="primary">{humanize(r.category)}</Badge> · created {formatTimestamp(r.created_at)} · key {r.key_id}
                  </div>
                  <div className="hash">ID {r.id}</div>
                </div>
                <div className="btn-row">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => view(r)}>Decrypt &amp; view</button>
                  {results[r.id] && (
                    <button type="button" className="btn btn-ghost btn-sm"
                            onClick={() => setResults(({ [r.id]: _removed, ...rest }) => rest)}>Hide</button>
                  )}
                </div>
              </div>
              <AccessResult result={results[r.id]} />
            </article>
          ))}
        </AsyncBlock>
      </section>
    </>
  );
}

function ProcessorAccess({ meta }) {
  const state = useApi("/records");
  const [request, setRequest] = useState({ record_id: "", purpose: "", action: "read" });
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(false);

  const submit = async (e) => {
    e?.preventDefault();
    setPending(true);
    setResult(null);
    try {
      const body = { action: request.action, purpose: request.purpose || undefined };
      setResult(await api(`/records/${encodeURIComponent(request.record_id.trim())}/access`, { method: "POST", body }));
    } catch (error) {
      setResult({ error });
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Request data access</h1>
          <p>Every request is evaluated by the backend against the subject's consents and logged, whether allowed or denied.</p>
        </div>
      </div>
      <div className="grid grid-2">
        <section className="card">
          <h2>Access request</h2>
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="req-record">Record ID</label>
              <input id="req-record" type="text" required maxLength={64} value={request.record_id}
                     onChange={(e) => setRequest({ ...request, record_id: e.target.value })} />
              <span className="help">Choose from the list or paste any ID (the backend decides).</span>
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="req-purpose">Purpose</label>
                <select id="req-purpose" required value={request.purpose}
                        onChange={(e) => setRequest({ ...request, purpose: e.target.value })}>
                  <option value="">Select…</option>
                  {meta?.purposes.map((p) => <option key={p.code} value={p.code}>{p.label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="req-action">Action</label>
                <select id="req-action" value={request.action} onChange={(e) => setRequest({ ...request, action: e.target.value })}>
                  {meta?.record_actions.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
            </div>
            <div><button className="btn" type="submit" disabled={pending}>{pending ? "Requesting…" : "Request access"}</button></div>
          </form>
          <div style={{ marginTop: 16 }} aria-live="polite"><AccessResult result={result} /></div>
        </section>
        <section className="card">
          <h2>Records from subjects who granted you consent</h2>
          <p className="small muted">Listed because the owner has granted you at least one consent (of any status). Listing does not imply access.</p>
          <AsyncBlock state={state} isEmpty={(d) => d.records.length === 0}
                      empty={<EmptyState title="No records available"><p>No subject has granted you consent yet.</p></EmptyState>}>
            {(d) => (
              <div className="table-wrap">
                <table>
                  <thead><tr><th scope="col">Label</th><th scope="col">Owner</th><th scope="col">Category</th><th scope="col" /></tr></thead>
                  <tbody>
                    {d.records.map((r) => (
                      <tr key={r.id}>
                        <td>{r.label}<div className="hash">{r.id}</div></td>
                        <td>{personLabel(r.owner)}</td>
                        <td><Badge tone="primary">{humanize(r.category)}</Badge></td>
                        <td>
                          <button type="button" className="btn btn-secondary btn-sm"
                                  onClick={() => setRequest((q) => ({ ...q, record_id: r.id }))}>Select</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </AsyncBlock>
        </section>
      </div>
    </>
  );
}

export default function RecordsPage() {
  const { user } = useAuth();
  const meta = useApi("/meta");
  return user.role === "subject" ? <SubjectRecords meta={meta.data} /> : <ProcessorAccess meta={meta.data} />;
}
