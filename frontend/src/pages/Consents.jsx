import { useEffect, useState } from "react";
import { api, formatTime } from "../api.js";

export default function Consents({ user }) {
  const [consents, setConsents] = useState([]);
  const [error, setError] = useState("");

  function load() {
    api("/consents")
      .then((data) => setConsents(data.consents))
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function withdraw(id) {
    if (!window.confirm("Withdraw this permission? The company will no longer see this data.")) return;
    try {
      await api(`/consents/${id}/withdraw`, "POST");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const title = { user: "My permissions", company: "Permissions given to us", investigator: "All permissions" };

  return (
    <>
      <h1>{title[user.role]}</h1>
      {user.role === "user" && <GiveConsentForm onSaved={load} />}
      {error && <p className="error">{error}</p>}
      <div className="card">
        {consents.length === 0 ? (
          <p className="muted">No permissions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Company</th>
                <th>Purpose</th>
                <th>Data types</th>
                <th>Status</th>
                <th>Ends</th>
                {user.role === "user" && <th></th>}
              </tr>
            </thead>
            <tbody>
              {consents.map((c) => (
                <tr key={c.id}>
                  <td>{c.user}</td>
                  <td>{c.company}</td>
                  <td>{c.purpose}</td>
                  <td>{c.categories.join(", ")}</td>
                  <td><span className={`tag ${c.status}`}>{c.status}</span></td>
                  <td>{c.expires_at ? formatTime(c.expires_at) : "never"}</td>
                  {user.role === "user" && (
                    <td>
                      {c.status === "active" && (
                        <button className="small-btn danger" onClick={() => withdraw(c.id)}>Withdraw</button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function GiveConsentForm({ onSaved }) {
  const [options, setOptions] = useState({ companies: [], purposes: [], categories: [] });
  const [form, setForm] = useState({ company_id: "", purpose: "", categories: [], days: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    api("/companies").then(setOptions).catch((err) => setError(err.message));
  }, []);

  function toggleCategory(category) {
    const categories = form.categories.includes(category)
      ? form.categories.filter((c) => c !== category)
      : [...form.categories, category];
    setForm({ ...form, categories });
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/consents", "POST", { ...form, company_id: Number(form.company_id) });
      setForm({ company_id: "", purpose: "", categories: [], days: "" });
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Give a new permission</h2>
      <div className="row">
        <label>
          Company
          <select value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
            <option value="">Choose...</option>
            {options.companies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label>
          Purpose
          <select value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
            <option value="">Choose...</option>
            {options.purposes.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Ends after (days, optional)
          <input value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} inputMode="numeric" />
        </label>
      </div>
      <fieldset>
        <legend>Which data may they use?</legend>
        {options.categories.map((c) => (
          <label key={c} className="check">
            <input type="checkbox" checked={form.categories.includes(c)} onChange={() => toggleCategory(c)} /> {c}
          </label>
        ))}
      </fieldset>
      {error && <p className="error">{error}</p>}
      <button type="submit">Give permission</button>
    </form>
  );
}
