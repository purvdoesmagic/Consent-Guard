import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import { LogTable } from "./ActivityLog.jsx";

export default function CaseDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [notes, setNotes] = useState("");
  const [ids, setIds] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function load() {
    api(`/cases/${id}`)
      .then((result) => {
        setData(result);
        setNotes(result.case.notes);
      })
      .catch((err) => setError(err.message));
  }
  useEffect(load, [id]);

  async function saveNotes() {
    await api(`/cases/${id}/notes`, "PUT", { notes });
    setMessage("Notes saved.");
  }

  async function addLogs(event) {
    event.preventDefault();
    const logIds = ids.split(",").map((s) => Number(s.trim())).filter(Boolean);
    await api(`/cases/${id}/logs`, "POST", { log_ids: logIds });
    setIds("");
    load();
  }

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>Loading...</p>;

  return (
    <>
      <h1>Case #{data.case.id}: {data.case.title}</h1>
      <p>{data.case.description}</p>

      <div className="card">
        <h2>Evidence (log entries)</h2>
        <LogTable logs={data.logs} />
        <form className="row" onSubmit={addLogs}>
          <label>
            Add log entries by number (e.g. 12, 13)
            <input value={ids} onChange={(e) => setIds(e.target.value)} />
          </label>
          <button type="submit">Add</button>
        </form>
      </div>

      <div className="card">
        <h2>Notes and conclusion</h2>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} />
        <button onClick={saveNotes}>Save notes</button> <span className="muted">{message}</span>
      </div>

      <a className="button" href={`/api/cases/${id}/report`}>Download PDF report</a>
    </>
  );
}
