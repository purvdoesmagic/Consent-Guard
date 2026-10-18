import { useEffect, useState } from "react";
import { api, formatTime, PURPOSE_TEXT } from "../api.js";

const PAGE = {
  user: ["My permissions", "Choose which company may use which of your data, and for what. You can withdraw any time."],
  company: ["Permissions given to us", "The users who allowed you to use their data, and what for."],
  investigator: ["All permissions", "Every permission in the system. You can see who allowed what, but not the data itself."],
};

export default function Consents({ user }) {
  const [consents, setConsents] = useState([]);
  const [error, setError] = useState("");

  function load() {
    api("/consents")
      .then((data) => setConsents(data.consents))
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function withdraw(consent) {
    const question = `Withdraw ${consent.company}'s permission for ${consent.purpose}? They will no longer see this data.`;
    if (!window.confirm(question)) return;
    try {
      await api(`/consents/${consent.id}/withdraw`, "POST");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const [title, subtitle] = PAGE[user.role];
  const showUser = user.role !== "user"; // a user doesn't need to see their own name in every row
  const showCompany = user.role !== "company";

  return (
    <>
      <h1>{title}</h1>
      <p className="subtitle">{subtitle}</p>
      {user.role === "user" && <GiveConsentForm onSaved={load} />}
      {error && <p className="error">{error}</p>}
      <div className="card">
        {consents.length === 0 ? (
          <p className="muted">No permissions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                {showUser && <th>User</th>}
                {showCompany && <th>Company</th>}
                <th>Purpose</th>
                <th>Data types</th>
                <th>Status</th>
                <th>Valid until</th>
                {user.role === "user" && <th></th>}
              </tr>
            </thead>
            <tbody>
              {consents.map((c) => (
                <tr key={c.id}>
                  {showUser && <td>{c.user}</td>}
                  {showCompany && <td>{c.company}</td>}
                  <td>{c.purpose}</td>
                  <td>{c.categories.join(", ")}</td>
                  <td><span className={`tag ${c.status}`}>{c.status}</span></td>
                  <td>{c.expires_at ? formatTime(c.expires_at) : "No end date"}</td>
                  {user.role === "user" && (
                    <td>
                      {c.status === "active" && (
                        <button className="small-btn danger" onClick={() => withdraw(c)}>Withdraw</button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="small muted legend">
          <span className="tag active">active</span> can be used ·{" "}
          <span className="tag withdrawn">withdrawn</span> taken back by the user ·{" "}
          <span className="tag expired">expired</span> end date has passed
        </p>
      </div>
    </>
  );
}

function GiveConsentForm({ onSaved }) {
  const [options, setOptions] = useState({ companies: [], purposes: [], categories: [] });
  const [form, setForm] = useState({ company_id: "", purpose: "", categories: [], days: "" });
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

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
    setMessage("");
    try {
      const { consent } = await api("/consents", "POST", { ...form, company_id: Number(form.company_id) });
      setForm({ company_id: "", purpose: "", categories: [], days: "" });
      setMessage(`Done. ${consent.company} may now use your ${consent.categories.join(", ")} data for ${consent.purpose}.`);
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
          Which company?
          <select value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
            <option value="">Choose...</option>
            {options.companies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label>
          For what purpose?
          <select value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
            <option value="">Choose...</option>
            {options.purposes.map((p) => (
              <option key={p} value={p}>{PURPOSE_TEXT[p] || p}</option>
            ))}
          </select>
        </label>
        <label>
          For how many days? (leave empty for no end date)
          <input value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} inputMode="numeric" />
        </label>
      </div>
      <fieldset>
        <legend>Which of your data may they use?</legend>
        {options.categories.map((c) => (
          <label key={c} className="check">
            <input type="checkbox" checked={form.categories.includes(c)} onChange={() => toggleCategory(c)} /> {c}
          </label>
        ))}
      </fieldset>
      {error && <p className="error">{error}</p>}
      {message && <p className="notice">{message}</p>}
      <button type="submit">Give permission</button>
    </form>
  );
}
