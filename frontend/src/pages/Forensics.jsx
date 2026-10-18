import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatTime, reasonText } from "../api.js";

// The forensic case study, step by step: Carol vs QuickLoans.
export default function Forensics() {
  const [copies, setCopies] = useState([]);
  const [caseId, setCaseId] = useState(null);
  const [coverUp, setCoverUp] = useState(null);
  const [check, setCheck] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function loadCopies() {
    api("/evidence")
      .then((data) => setCopies(data.copies))
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    loadCopies();
    api("/cases").then((data) => {
      const carol = data.cases.find((c) => c.title.includes("Carol"));
      if (carol) setCaseId(carol.id);
    });
  }, []);

  const latest = copies[copies.length - 1];

  async function run(action) {
    setError("");
    setMessage("");
    try {
      await action();
    } catch (err) {
      setError(err.message);
    }
  }

  const saveCopy = () =>
    run(async () => {
      const data = await api("/evidence", "POST", { note: "Saved before writing the report" });
      setMessage(`Evidence copy ${data.copy.id} saved.`);
      setComparison(null);
      loadCopies();
    });

  const doCoverUp = () =>
    run(async () => {
      if (!window.confirm("This simulates an insider deleting QuickLoans' blocked attempts directly in the database. Continue?")) return;
      setCoverUp(await api("/demo/cover-up", "POST", { company: "quickloans" }));
      setCheck(null);
      setComparison(null);
    });

  const checkLog = () => run(async () => setCheck(await api("/logs/verify")));

  const compare = (copy) => run(async () => setComparison(await api(`/evidence/${copy.id}/compare`, "POST")));

  const restore = (copy) =>
    run(async () => {
      if (!window.confirm(`Put evidence copy ${copy.id} back? This undoes everything done after it was saved.`)) return;
      const data = await api(`/evidence/${copy.id}/restore`, "POST");
      setMessage(data.message);
      setCoverUp(null);
      setCheck(null);
      setComparison(null);
    });

  return (
    <>
      <h1>Forensics: Carol's case</h1>
      <p className="subtitle">A step-by-step digital forensics investigation using the activity log.</p>

      <div className="card story">
        <h2>The complaint</h2>
        <p>
          Carol let <strong>QuickLoans</strong> use her financial and contact data for her loan. Later she got
          marketing calls, so she <strong>withdrew her permission</strong>. The calls continued, and she complained.
        </p>
        <p className="muted">
          Questions: Did QuickLoans see her data after she said stop? Did it try anything else? Can we trust the log?
        </p>
      </div>

      {message && <p className="notice">{message}</p>}
      {error && <p className="error">{error}</p>}

      <Step number="1" title="Look at the evidence">
        <p>Open the case to see every attempt QuickLoans made, and check the alerts.</p>
        {caseId && <Link className="button secondary" to={`/cases/${caseId}`}>Open Carol's case</Link>}{" "}
        <Link className="button secondary" to="/alerts">See alerts</Link>
      </Step>

      <Step number="2" title="Save an evidence copy">
        <p>
          Like sealing evidence in a bag: copy the whole database and write down its SHA-256 fingerprint and the
          last log hash. This copy is kept outside the live system.
        </p>
        <button onClick={saveCopy}>Save evidence copy</button>
        {latest && (
          <div className="result neutral">
            Copy {latest.id} saved {formatTime(latest.saved_at)}: <strong>{latest.entries} log entries</strong>
            <div className="hash small">Last log hash: {latest.last_hash}</div>
            <div className="hash small">File SHA-256: {latest.file_sha256}</div>
          </div>
        )}
      </Step>

      <Step number="3" title="Insider tampering (simulation)" warning>
        <p>
          Now we play the attacker: someone with direct database access deletes QuickLoans' blocked attempts and
          recalculates every hash so the chain looks fine.
        </p>
        <button className="danger" onClick={doCoverUp} disabled={!latest}>Simulate the cover-up</button>
        {!latest && <span className="muted small"> Save an evidence copy first.</span>}
        {coverUp && (
          <div className="result blocked">
            {coverUp.removed > 0
              ? `${coverUp.removed} log entries were secretly deleted and all hashes were recalculated.`
              : "Nothing to delete (the cover-up was already done)."}
          </div>
        )}
      </Step>

      <Step number="4" title="Check the log the normal way">
        <p>The app's own hash-chain check walks through every entry.</p>
        <button onClick={checkLog}>Check the log</button>
        {check && (
          <div className={`result ${check.valid ? "allowed" : "blocked"}`}>
            <strong>{check.valid ? "VALID" : "INVALID"}</strong> ({check.count} entries)
            {check.valid && coverUp?.removed > 0 && (
              <p>The check was fooled, because the attacker recalculated every hash.</p>
            )}
          </div>
        )}
      </Step>

      <Step number="5" title="Compare with the evidence copy">
        <p>Now compare the live log with the copy we saved in step 2.</p>
        <button onClick={() => compare(latest)} disabled={!latest}>Compare with copy {latest?.id}</button>
        {comparison && <ComparisonResult result={comparison} />}
      </Step>

      <Step number="6" title="Restore the evidence copy">
        <p>Put the evidence copy back to undo the tampering.</p>
        <button className="secondary" onClick={() => restore(latest)} disabled={!latest}>
          Restore copy {latest?.id}
        </button>
      </Step>

      {copies.length > 0 && (
        <div className="card">
          <h2>All evidence copies</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Saved</th>
                <th>By</th>
                <th>Entries</th>
                <th>Note</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {copies.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{formatTime(c.saved_at)}</td>
                  <td>{c.saved_by}</td>
                  <td>{c.entries}</td>
                  <td>{c.note}</td>
                  <td className="nowrap">
                    <button className="small-btn" onClick={() => compare(c)}>Compare</button>{" "}
                    <button className="small-btn secondary" onClick={() => restore(c)}>Restore</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Step({ number, title, warning, children }) {
  return (
    <div className={`card step${warning ? " warning" : ""}`}>
      <div className="step-number">{number}</div>
      <div className="step-body">
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ComparisonResult({ result }) {
  return (
    <div className={`result ${result.tampered ? "blocked" : "allowed"}`}>
      <ul className="checklist">
        <li>{result.copy_unchanged ? "✔" : "✘"} The evidence copy itself is unchanged</li>
        <li>
          {result.last_hash_found ? "✔" : "✘"} The last hash we wrote down
          {result.last_hash_found ? " still exists" : " no longer exists in the live log"}
        </li>
        <li>
          {result.missing.length === 0 ? "✔" : "✘"} Entries missing from the live log: {result.missing.length}
          {" "}(copy had {result.copy.entries}, live log has {result.live_entries})
        </li>
      </ul>
      {result.tampered ? (
        <p><strong>The log was tampered with.</strong> These entries were deleted:</p>
      ) : (
        <p><strong>No tampering found.</strong> Everything in the copy is still in the live log.</p>
      )}
      {result.missing.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Who</th>
              <th>Action</th>
              <th>Result</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {result.missing.map((m, i) => (
              <tr key={i}>
                <td className="nowrap">{formatTime(m.time)}</td>
                <td>{m.who}</td>
                <td>{m.action} ({m.details})</td>
                <td><span className="tag denied">{m.result}</span></td>
                <td>{reasonText(m.reason)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {result.tampered && (
        <p className="conclusion">
          Conclusion: QuickLoans got no data after Carol withdrew permission (every attempt was blocked), but someone
          deleted exactly those blocked attempts. The evidence copy proves it.
        </p>
      )}
    </div>
  );
}
