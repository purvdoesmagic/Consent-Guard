import { useEffect, useState } from "react";
import { api, reasonText } from "../api.js";

export default function Records({ user }) {
  const [records, setRecords] = useState([]);
  const [purposes, setPurposes] = useState([]);
  const [categories, setCategories] = useState([]);
  const [purpose, setPurpose] = useState("");
  const [shown, setShown] = useState(null); // result of the last "view" click
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

  async function view(record) {
    setShown(null);
    try {
      const data = await api(`/records/${record.id}/view`, "POST", { purpose });
      setShown({ record, content: data.content });
    } catch (err) {
      setShown({ record, blocked: err.data?.reason || err.message });
    }
  }

  const isCompany = user.role === "company";

  return (
    <>
      <h1>{isCompany ? "Request data" : "My data"}</h1>
      {!isCompany && <AddRecordForm categories={categories} onSaved={load} />}
      {isCompany && (
        <div className="card">
          <label>
            Why do you need the data? (purpose)
            <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              <option value="">Choose...</option>
              {purposes.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <p className="muted small">You only see the data if the user gave you permission for this purpose.</p>
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {shown && (
        <div className={`card ${shown.blocked ? "blocked" : "allowed"}`}>
          <strong>{shown.record.title}</strong> ({shown.record.owner})
          {shown.blocked ? <p>Blocked: {reasonText(shown.blocked)}</p> : <p>{shown.content}</p>}
        </div>
      )}

      <div className="card">
        {records.length === 0 ? (
          <p className="muted">{isCompany ? "No user has given you permission yet." : "You have not added any data yet."}</p>
        ) : (
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
                    <button className="small-btn" onClick={() => view(r)} disabled={isCompany && !purpose}>
                      {isCompany ? "Request" : "View"}
                    </button>
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
      <p className="muted small">Use fake data only. The content is encrypted before it is saved.</p>
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
