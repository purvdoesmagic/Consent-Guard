import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

// Sample accounts created by backend/seed.py (shown only when "Use a sample account" is clicked)
const SAMPLE_PASSWORD = "Demo-Password-2026!";
const SAMPLE_ACCOUNTS = [
  ["alice", "User"],
  ["carol", "User"],
  ["brightads", "Company"],
  ["quickloans", "Company"],
  ["ivy", "Investigator"],
];

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [error, setError] = useState("");
  const [showSamples, setShowSamples] = useState(false);

  async function logIn(name, pass) {
    setError("");
    try {
      const data = await api("/login", "POST", { username: name, password: pass, code });
      onLogin(data.user);
    } catch (err) {
      if (err.data?.need_code) setNeedCode(true);
      setError(err.message);
    }
  }

  function submit(event) {
    event.preventDefault();
    logIn(username, password);
  }

  function signInAs(name) {
    setUsername(name);
    setPassword(SAMPLE_PASSWORD);
    logIn(name, SAMPLE_PASSWORD);
  }

  return (
    <div className="login-page">
      <div className="login-intro">
        <div className="logo">ConsentGuard</div>
        <h1>You decide who uses your data.</h1>
        <ul>
          <li>Give companies permission for a specific purpose, and take it back at any time</li>
          <li>Every request is checked against your permission and saved in a log</li>
          <li>The log is hash-chained, so tampering can be detected and investigated</li>
        </ul>
      </div>

      <div className="login-box">
        <h2>Log in</h2>
        <form onSubmit={submit}>
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {needCode && (
            <label>
              6-digit code from your authenticator app
              <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} />
            </label>
          )}
          {error && <p className="error">{error}</p>}
          <button type="submit">Log in</button>
        </form>
        <p>
          No account? <Link to="/register">Register</Link>
        </p>

        <button type="button" className="link-button" onClick={() => setShowSamples(!showSamples)}>
          {showSamples ? "Hide sample accounts" : "Use a sample account"}
        </button>
        {showSamples && (
          <div className="sample-accounts">
            {SAMPLE_ACCOUNTS.map(([name, role]) => (
              <button key={name} type="button" className="chip" onClick={() => signInAs(name)}>
                {name} <small>{role}</small>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
