import { useEffect, useState } from "react";
import { api, formatTime, reasonText } from "../api.js";

export function LogTable({ logs }) {
  if (logs.length === 0) return <p className="muted">No entries.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Time</th>
          <th>Who</th>
          <th>Action</th>
          <th>On</th>
          <th>Result</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
        {logs.map((e) => (
          <tr key={e.id}>
            <td>{e.id}</td>
            <td className="nowrap">{formatTime(e.time)}</td>
            <td>{e.who}</td>
            <td>{e.action}</td>
            <td>{e.owner ? `${e.owner}'s ${e.target}` : e.target}</td>
            <td><span className={`tag ${e.result}`}>{e.result}</span></td>
            <td>{reasonText(e.reason)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ActivityLog() {
  const [logs, setLogs] = useState([]);
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/logs")
      .then((data) => setLogs(data.logs))
      .catch((err) => setError(err.message));
  }, []);

  async function verify() {
    try {
      setCheck(await api("/logs/verify"));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <h1>Activity log</h1>
      <div className="card">
        <p>Every entry is linked to the one before it. Click below to check that nothing was changed or deleted.</p>
        <button onClick={verify}>Check the log</button>
        {check && (
          <div className={`result ${check.valid ? "allowed" : "blocked"}`}>
            <strong>{check.valid ? "VALID: no changes found" : "INVALID: the log was changed"}</strong>
            <span className="small"> ({check.count} entries checked)</span>
            <ul>
              {check.problems.map((p, i) => (
                <li key={i}>Entry {p.id}: {p.problem}</li>
              ))}
            </ul>
            <div className="small muted hash">Last hash: {check.last_hash}</div>
          </div>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <LogTable logs={logs} />
      </div>
    </>
  );
}
