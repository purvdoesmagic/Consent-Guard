import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const data = await api("/login", "POST", { username, password, code });
      onLogin(data.user);
    } catch (err) {
      if (err.data?.need_code) setNeedCode(true);
      setError(err.message);
    }
  }

  return (
    <div className="login-box">
      <h1>ConsentGuard</h1>
      <p className="muted">Control who can use your personal data.</p>
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
      <p className="muted small">Demo accounts: alice, bob, acme, brightads, ivy (password Demo-Password-2026!)</p>
    </div>
  );
}
