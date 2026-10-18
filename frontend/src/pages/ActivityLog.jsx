import { useEffect, useState } from "react";
import { api, formatTime } from "../api.js";

export function LogTable({ logs }) {
  if (logs.length === 0) return <p className="muted">No entries.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Time</th>
          <th>Who</th>
          <th>What happened</th>
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
            <td>{e.what}</td>
            <td>{e.on}</td>
            <td><span className={`tag ${e.result}`}>{e.result_text}</span></td>
            <td>{e.reason_text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const FILTERS = {
  all: ["All", () => true],
  allowed: ["Allowed", (e) => e.result === "allowed"],
  blocked: ["Blocked", (e) => e.result === "denied"],
  logins: ["Logins", (e) => e.action === "login"],
};

export default function ActivityLog() {
  const [logs, setLogs] = useState([]);
  const [check, setCheck] = useState(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  const text = search.toLowerCase();
  const shown = logs.filter(FILTERS[filter][1]).filter((e) =>
    [e.who, e.what, e.on, e.reason_text].join(" ").toLowerCase().includes(text),
  );

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
      <p className="subtitle">Everything that happens is saved here, including blocked requests.</p>
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
        <div className="toolbar">
          {Object.entries(FILTERS).map(([key, [label]]) => (
            <button key={key} className={`chip${filter === key ? " selected" : ""}`} onClick={() => setFilter(key)}>
              {label}
            </button>
          ))}
          <input
            className="search"
            placeholder="Search, e.g. BrightAds or withdrawn"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <p className="small muted">Showing {shown.length} of {logs.length} entries</p>
        <LogTable logs={shown} />
      </div>
    </>
  );
}
