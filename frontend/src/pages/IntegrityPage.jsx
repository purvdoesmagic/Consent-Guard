import { useState } from "react";
import { Badge } from "../components/Badge.jsx";
import { AsyncBlock, ErrorAlert } from "../components/Feedback.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { api } from "../services/api.js";
import { formatTimestamp } from "../utils/format.js";

function Result({ result }) {
  return (
    <>
      <div className={`alert ${result.valid ? "alert-success" : "alert-error"}`} role="status">
        <strong>{result.valid ? "Chain verified: no integrity findings." : `Verification failed: ${result.findings?.length ?? result.finding_count} finding(s).`}</strong>
        <span className="ref">Checked {formatTimestamp(result.checked_at)} · {result.event_count} events · head seq {result.head_seq}</span>
      </div>
      {result.head_hash && (
        <dl className="dl small">
          <dt>Chain head hash</dt><dd className="hash">{result.head_hash}</dd>
          {result.last_checkpoint && (
            <>
              <dt>Last checkpoint</dt>
              <dd>seq {result.last_checkpoint.head_seq} at {formatTimestamp(result.last_checkpoint.created_at)}</dd>
            </>
          )}
        </dl>
      )}
      {result.findings?.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 14 }}>
          <table>
            <thead><tr><th scope="col">Finding</th><th scope="col">Seq</th><th scope="col">Event ID</th><th scope="col">Meaning</th></tr></thead>
            <tbody>
              {result.findings.map((f, i) => (
                <tr key={i}>
                  <td><Badge tone="danger">{f.type}</Badge></td>
                  <td>#{f.seq}</td>
                  <td className="mono small">{f.event_id ?? "—"}</td>
                  <td>{f.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function IntegrityPage() {
  const { user } = useAuth();
  const status = useApi("/audit/integrity");
  const [verified, setVerified] = useState(null);
  const action = useAction();
  const investigator = user.role === "investigator";

  const verify = async () => {
    const result = await action.run(() => api("/audit/verify", { method: "POST" }));
    if (result) {
      setVerified(result);
      status.reload();
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Audit integrity</h1>
          <p>Each event stores the SHA-256 hash of its predecessor. Verification recomputes every hash and link.</p>
        </div>
        {investigator && (
          <button type="button" className="btn" onClick={verify} disabled={action.pending}>
            {action.pending ? "Verifying…" : "Run verification & record checkpoint"}
          </button>
        )}
      </div>
      <ErrorAlert error={action.error} />
      <div className="grid grid-2">
        <section className="card">
          <h2>{verified ? "Verification result" : "Current status"}</h2>
          {verified ? <Result result={verified} /> : (
            <AsyncBlock state={status}>{(d) => <Result result={d} />}</AsyncBlock>
          )}
          {!investigator && (
            <p className="small muted" style={{ marginTop: 12 }}>Detailed findings and checkpoints are available to investigators.</p>
          )}
        </section>
        <section className="card">
          <h2>What this check proves</h2>
          {status.data && (
            <>
              <ul className="finding-list">
                {status.data.explanation.proves.map((t) => <li key={t}>{t}</li>)}
              </ul>
              <h3 style={{ marginTop: 16 }}>What it does not prove</h3>
              <ul className="finding-list">
                {status.data.explanation.does_not_prove.map((t) => <li key={t}>{t}</li>)}
              </ul>
              <p className="small muted" style={{ marginTop: 12 }}>
                Stronger guarantees require copying signed checkpoints (for example the head hash printed in every PDF
                report) to an independently controlled system.
              </p>
            </>
          )}
        </section>
      </div>
    </>
  );
}
