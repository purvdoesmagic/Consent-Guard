import { useEffect, useState } from "react";
import { api, reasonText } from "../api.js";

export default function Records({ user }) {
  const [records, setRecords] = useState([]);
  const [purposes, setPurposes] = useState([]);
  const [categories, setCategories] = useState([]);
  const [shown, setShown] = useState(null); // result of the last View/Request click
  const [error, setError] = useState("");

  function load() {
    api("/records")
      .then((data) => {
        setRecords(data.records);
        setPurposes(data.purposes);
        setCategories(data.categories);
      })
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function view(record, purpose) {
    setShown(null);
    try {
      const data = await api(`/records/${record.id}/view`, "POST", { purpose });
      setShown({ record, content: data.content });
    } catch (err) {
      setShown({ record, blocked: err.data?.reason || err.message });
    }
  }

  const result = shown && (
    <div className={`card ${shown.blocked ? "blocked" : "allowed"}`}>
      <strong>{shown.record.title}</strong> ({shown.record.owner})
      {shown.blocked ? <p>Blocked: {reasonText(shown.blocked)}</p> : <p>{shown.content}</p>}
    </div>
  );

  if (user.role === "company") {
    const shared = records.filter((r) => r.allowed_purposes.length > 0);
    const notShared = records.filter((r) => r.allowed_purposes.length === 0);
    return (
      <>
        <h1>Request data</h1>
        <p className="subtitle">You can only see a user's data for the purpose they gave you permission for.</p>
        {error && <p className="error">{error}</p>}
        {result}
        <SharedRecords records={shared} onView={view} />
        <NotSharedRecords records={notShared} purposes={purposes} onRequest={view} />
      </>
    );
  }

  return (
    <>
      <h1>My data</h1>
      <p className="subtitle">Your personal data, stored encrypted. Companies only see it with your permission.</p>
      <AddRecordForm categories={categories} onSaved={load} />
      {error && <p className="error">{error}</p>}
      {result}
      <div className="card">
        {records.length === 0 ? (
          <p className="muted">You have not added any data yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td>{r.title}</td>
                  <td>{r.category}</td>
                  <td>
                    <button className="small-btn" onClick={() => view(r)}>View</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function SharedRecords({ records, onView }) {
  return (
    <div className="card">
      <h2>Shared with you ({records.length})</h2>
      {records.length === 0 ? (
        <p className="muted">No user has shared any data with you yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Owner</th>
              <th>Allowed for</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>{r.category}</td>
                <td>{r.owner}</td>
                <td className="nowrap">
                  {r.allowed_purposes.map((p) => (
                    <button key={p} className="small-btn" onClick={() => onView(r, p)}>View for {p}</button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function NotSharedRecords({ records, purposes, onRequest }) {
  const [purpose, setPurpose] = useState("");
  if (records.length === 0) return null;
  return (
    <div className="card">
      <h2>Not shared with you ({records.length})</h2>
      <p className="muted small">
        These users have not allowed you to use this data (or their permission was withdrawn or has expired).
        A request will be blocked and recorded in the activity log.
      </p>
      <label className="inline-label">
        Request with purpose
        <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
          <option value="">Choose...</option>
          {purposes.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </label>
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Type</th>
            <th>Owner</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id}>
              <td>{r.title}</td>
              <td>{r.category}</td>
              <td>{r.owner}</td>
              <td>
                <button className="small-btn secondary" onClick={() => onRequest(r, purpose)} disabled={!purpose}>
                  Request
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AddRecordForm({ categories, onSaved }) {
  const [form, setForm] = useState({ title: "", category: "", content: "" });
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/records", "POST", form);
      setForm({ title: "", category: "", content: "" });
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Add personal data</h2>
      <p className="muted small">The content is encrypted before it is saved.</p>
      <div className="row">
        <label>
          Title
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </label>
        <label>
          Type
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">Choose...</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Content
        <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} rows={3} />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit">Save</button>
    </form>
  );
}
