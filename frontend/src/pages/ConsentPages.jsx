import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { StatusBadge } from "../components/Badge.jsx";
import { Alert, AsyncBlock, EmptyState, ErrorAlert, Loading } from "../components/Feedback.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { api } from "../services/api.js";
import { formatTimestamp, humanize, personLabel, toIsoFromLocalInput } from "../utils/format.js";

const STATUS_FILTERS = ["all", "active", "withdrawn", "expired"];

function labelFor(list, code) {
  return list?.find((x) => x.code === code)?.label ?? humanize(code);
}

export function ConsentsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState("all");
  const state = useApi(`/consents${status === "all" ? "" : `?status=${status}`}`);
  const meta = useApi("/meta");

  const title = { subject: "My consents", processor: "Consents granted to me", investigator: "Consent registry" }[user.role];
  return (
    <>
      <div className="page-header">
        <div>
          <h1>{title}</h1>
          <p>
            {user.role === "subject"
              ? "Each consent allows one processor to use specific data categories for one purpose."
              : user.role === "processor"
                ? "You may only access data covered by an active consent for the stated purpose."
                : "Read-only view of all consents for investigation."}
          </p>
        </div>
        {user.role === "subject" && <Link className="btn" to="/consents/new">New consent</Link>}
      </div>
      <div className="card">
        <div className="card-header">
          <div className="filter-pills" role="group" aria-label="Filter by status">
            {STATUS_FILTERS.map((s) => (
              <button key={s} type="button" className="pill" aria-pressed={status === s} onClick={() => setStatus(s)}>
                {humanize(s)}
              </button>
            ))}
          </div>
        </div>
        <AsyncBlock
          state={state}
          isEmpty={(d) => d.consents.length === 0}
          empty={
            <EmptyState title="No consents found">
              {user.role === "subject" && <p>Create a consent to allow a processor to use your data.</p>}
            </EmptyState>
          }
        >
          {(d) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">ID</th>
                    {user.role !== "subject" && <th scope="col">Subject</th>}
                    {user.role !== "processor" && <th scope="col">Recipient</th>}
                    <th scope="col">Purpose</th>
                    <th scope="col">Categories</th>
                    <th scope="col">Status</th>
                    <th scope="col">Expires</th>
                    <th scope="col"><span className="visually-hidden">Open</span></th>
                  </tr>
                </thead>
                <tbody>
                  {d.consents.map((c) => (
                    <tr key={c.id}>
                      <td>#{c.id}</td>
                      {user.role !== "subject" && <td>{personLabel(c.subject)}</td>}
                      {user.role !== "processor" && <td>{personLabel(c.recipient)}</td>}
                      <td>{labelFor(meta.data?.purposes, c.purpose)}</td>
                      <td>{c.categories.map((cat) => labelFor(meta.data?.categories, cat)).join(", ")}</td>
                      <td><StatusBadge status={c.status} /></td>
                      <td className="nowrap">{c.expires_at ? formatTimestamp(c.expires_at, { seconds: false }) : "No expiry"}</td>
                      <td><Link to={`/consents/${c.id}`}>View</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBlock>
      </div>
    </>
  );
}

function CategoryChecks({ categories, value, onChange, idPrefix }) {
  const toggle = (code) => onChange(value.includes(code) ? value.filter((c) => c !== code) : [...value, code]);
  return (
    <fieldset>
      <legend>Data categories</legend>
      <div className="checkbox-group">
        {categories.map((c) => (
          <label key={c.code} className="checkbox" htmlFor={`${idPrefix}-${c.code}`}>
            <input id={`${idPrefix}-${c.code}`} type="checkbox" checked={value.includes(c.code)} onChange={() => toggle(c.code)} />
            {c.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function ConsentCreatePage() {
  const meta = useApi("/meta");
  const processors = useApi("/processors");
  const [form, setForm] = useState({ recipient_id: "", purpose: "", categories: [], expires_at: "" });
  const action = useAction();
  const navigate = useNavigate();

  if (meta.loading || processors.loading) return <Loading />;
  if (meta.error || processors.error) return <ErrorAlert error={meta.error || processors.error} />;

  const submit = async (e) => {
    e.preventDefault();
    const body = {
      recipient_id: Number(form.recipient_id),
      purpose: form.purpose,
      categories: form.categories,
    };
    if (form.expires_at) body.expires_at = toIsoFromLocalInput(form.expires_at);
    const result = await action.run(() => api("/consents", { method: "POST", body }));
    if (result) navigate(`/consents/${result.consent.id}`, { state: { created: true } });
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>New consent</h1>
          <p>Grant one processor permission to use selected data categories for a single purpose.</p>
        </div>
      </div>
      <div className="card">
        <ErrorAlert error={action.error} />
        {processors.data.processors.length === 0 ? (
          <EmptyState title="No processors registered">
            <p>A data processor account must exist before consent can be granted.</p>
          </EmptyState>
        ) : (
          <form className="form" onSubmit={submit}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="c-recipient">Recipient (data processor)</label>
                <select id="c-recipient" required value={form.recipient_id}
                        onChange={(e) => setForm({ ...form, recipient_id: e.target.value })}>
                  <option value="">Select a processor…</option>
                  {processors.data.processors.map((p) => <option key={p.id} value={p.id}>{p.display_name} ({p.username})</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="c-purpose">Purpose</label>
                <select id="c-purpose" required value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
                  <option value="">Select a purpose…</option>
                  {meta.data.purposes.map((p) => <option key={p.code} value={p.code}>{p.label}</option>)}
                </select>
                <span className="help">The purpose cannot be changed later; a new purpose needs a new consent.</span>
              </div>
            </div>
            <CategoryChecks idPrefix="new" categories={meta.data.categories} value={form.categories}
                            onChange={(categories) => setForm({ ...form, categories })} />
            <div className="field" style={{ maxWidth: 320 }}>
              <label htmlFor="c-expiry">Expires (optional, your local time)</label>
              <input id="c-expiry" type="datetime-local" value={form.expires_at}
                     onChange={(e) => setForm({ ...form, expires_at: e.target.value })} />
              <span className="help">Stored in UTC. Leave blank for consent valid until withdrawn.</span>
            </div>
            <div className="btn-row">
              <button className="btn" type="submit" disabled={action.pending || form.categories.length === 0}>
                {action.pending ? "Granting…" : "Grant consent"}
              </button>
              <Link className="btn btn-secondary" to="/consents">Cancel</Link>
            </div>
          </form>
        )}
      </div>
    </>
  );
}

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ConsentDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const state = useApi(`/consents/${id}`);
  const meta = useApi("/meta");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(null);
  const action = useAction();

  const startEdit = (consent) => {
    setForm({ categories: consent.categories, expires_at: toLocalInput(consent.expires_at), clear: false });
    setEditing(true);
    action.reset();
  };

  const save = async (e, consent) => {
    e.preventDefault();
    const body = {};
    if (JSON.stringify([...form.categories].sort()) !== JSON.stringify(consent.categories)) body.categories = form.categories;
    if (form.clear) body.clear_expiry = true;
    else if (form.expires_at && toIsoFromLocalInput(form.expires_at) !== consent.expires_at) {
      body.expires_at = toIsoFromLocalInput(form.expires_at);
    }
    const result = await action.run(() => api(`/consents/${id}`, { method: "PATCH", body }), "Consent updated.");
    if (result) {
      setEditing(false);
      state.reload();
    }
  };

  const withdraw = async () => {
    if (!window.confirm("Withdraw this consent? The processor will immediately lose access. This cannot be undone.")) return;
    const result = await action.run(() => api(`/consents/${id}/withdraw`, { method: "POST" }), "Consent withdrawn.");
    if (result) state.reload();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Consent #{id}</h1>
          <p><Link to="/consents">← Back to consents</Link></p>
        </div>
      </div>
      <Alert tone="success">{action.success}</Alert>
      <ErrorAlert error={action.error} />
      <AsyncBlock state={state}>
        {({ consent }) => {
          const canModify = user.role === "subject" && consent.subject.id === user.id && consent.status === "active";
          return (
            <div className="grid grid-2">
              <section className="card">
                <div className="card-header">
                  <h2>Details</h2>
                  <StatusBadge status={consent.status} />
                </div>
                <dl className="dl">
                  <dt>Data subject</dt><dd>{personLabel(consent.subject)}</dd>
                  <dt>Recipient</dt><dd>{personLabel(consent.recipient)}</dd>
                  <dt>Purpose</dt><dd>{labelFor(meta.data?.purposes, consent.purpose)}</dd>
                  <dt>Data categories</dt><dd>{consent.categories.map((c) => labelFor(meta.data?.categories, c)).join(", ")}</dd>
                  <dt>Version</dt><dd>{consent.version}</dd>
                  <dt>Created</dt><dd>{formatTimestamp(consent.created_at)}</dd>
                  <dt>Last modified</dt><dd>{formatTimestamp(consent.updated_at)}</dd>
                  <dt>Expires</dt><dd>{consent.expires_at ? formatTimestamp(consent.expires_at) : "No expiry"}</dd>
                  {consent.withdrawn_at && (<><dt>Withdrawn</dt><dd>{formatTimestamp(consent.withdrawn_at)}</dd></>)}
                  {consent.expired_at && (<><dt>Expired</dt><dd>{formatTimestamp(consent.expired_at)}</dd></>)}
                </dl>
                {canModify && !editing && (
                  <div className="btn-row" style={{ marginTop: 16 }}>
                    <button type="button" className="btn btn-secondary" onClick={() => startEdit(consent)}>Edit preferences</button>
                    <button type="button" className="btn btn-danger" onClick={withdraw} disabled={action.pending}>Withdraw consent</button>
                  </div>
                )}
                {consent.status !== "active" && (
                  <p className="small muted" style={{ marginTop: 14 }}>
                    This consent is {consent.status} and can no longer authorize access or be modified.
                  </p>
                )}
                {editing && meta.data && (
                  <form className="form" style={{ marginTop: 18 }} onSubmit={(e) => save(e, consent)}>
                    <h3>Edit preferences</h3>
                    <CategoryChecks idPrefix="edit" categories={meta.data.categories} value={form.categories}
                                    onChange={(categories) => setForm({ ...form, categories })} />
                    <div className="field">
                      <label htmlFor="e-expiry">Expires (your local time)</label>
                      <input id="e-expiry" type="datetime-local" value={form.expires_at} disabled={form.clear}
                             onChange={(e) => setForm({ ...form, expires_at: e.target.value })} />
                    </div>
                    <label className="checkbox">
                      <input type="checkbox" checked={form.clear} onChange={(e) => setForm({ ...form, clear: e.target.checked })} />
                      Remove expiry (valid until withdrawn)
                    </label>
                    <div className="btn-row">
                      <button className="btn" type="submit" disabled={action.pending || form.categories.length === 0}>Save changes</button>
                      <button className="btn btn-secondary" type="button" onClick={() => setEditing(false)}>Cancel</button>
                    </div>
                  </form>
                )}
              </section>
              <section className="card">
                <h2>History</h2>
                <p className="small muted">Append-only snapshots written on every lifecycle change.</p>
                <ul className="timeline">
                  {consent.history.map((h) => (
                    <li key={h.version}>
                      <span className={`dot ${h.change_type === "withdrawn" ? "denied" : h.change_type === "expired" ? "" : "consent"}`} />
                      <div className="when">{formatTimestamp(h.changed_at)}</div>
                      <div className="what">v{h.version} · {humanize(h.change_type)} <StatusBadge status={h.status} /></div>
                      <div className="small muted">
                        Categories: {h.categories.join(", ")} · Expires: {h.expires_at ? formatTimestamp(h.expires_at) : "none"} ·
                        By: {h.changed_by === null ? "system (automatic expiry)" : `user #${h.changed_by}`}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          );
        }}
      </AsyncBlock>
    </>
  );
}
