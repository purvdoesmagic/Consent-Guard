import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatTime } from "../api.js";

export default function Alerts() {
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api("/alerts")
      .then((data) => setAlerts(data.alerts))
      .catch((err) => setError(err.message));
  }, []);

  async function openCase(alert) {
    try {
      const { case: created } = await api("/cases", "POST", { title: alert.title, description: alert.explanation });
      await api(`/cases/${created.id}/logs`, "POST", { log_ids: alert.log_ids });
      navigate(`/cases/${created.id}`);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <h1>Alerts</h1>
      <p className="subtitle">Suspicious activity found in the log by four simple rules. An alert is a lead to check, not proof.</p>
      <div className="card rules">
        <strong>The rules:</strong>
        <span>R1 Many blocked attempts (3+ in 10 min)</span>
        <span>R2 Tried after permission was withdrawn</span>
        <span>R3 Wrong purpose or data type</span>
        <span>R4 Many wrong passwords (5+ in 10 min)</span>
      </div>
      {error && <p className="error">{error}</p>}
      {alerts && alerts.length === 0 && <p>No alerts.</p>}
      {alerts?.map((a, i) => (
        <div key={i} className="card">
          <span className={`tag ${a.severity}`}>{a.severity}</span> <strong>{a.rule}: {a.title}</strong>
          <p>{a.explanation}</p>
          <p className="small muted">
            Log entries: {a.log_ids.join(", ")} · first seen {formatTime(a.first_time)}
          </p>
          <button className="small-btn" onClick={() => openCase(a)}>Open a case for this</button>
        </div>
      ))}
    </>
  );
}
