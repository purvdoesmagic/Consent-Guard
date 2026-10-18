import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatTime } from "../api.js";

export default function Cases() {
  const [cases, setCases] = useState([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  function load() {
    api("/cases")
      .then((data) => setCases(data.cases))
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/cases", "POST", { title, description });
      setTitle("");
      setDescription("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <h1>Cases</h1>
      <form className="card" onSubmit={create}>
        <h2>New case</h2>
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Description
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit">Create case</button>
      </form>
      <div className="card">
        {cases.length === 0 ? (
          <p className="muted">No cases yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Title</th>
                <th>Opened</th>
                <th>Log entries</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td><Link to={`/cases/${c.id}`}>{c.title}</Link></td>
                  <td>{formatTime(c.created_at)}</td>
                  <td>{c.log_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
