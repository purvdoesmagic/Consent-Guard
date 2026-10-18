import { useState } from "react";
import { api } from "../api.js";

export default function Account({ user, onChange }) {
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  async function start() {
    setError("");
    setSetup(await api("/two-step/setup", "POST"));
  }

  async function enable(event) {
    event.preventDefault();
    setError("");
    try {
      const data = await api("/two-step/enable", "POST", { code });
      setSetup(null);
      onChange(data.user);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <h1>Account</h1>
      <div className="card">
        <p>
          <strong>{user.name}</strong> (@{user.username}, {user.role})
        </p>
      </div>
      <div className="card">
        <h2>Two-step login</h2>
        {user.two_step_enabled ? (
          <p className="allowed result">Two-step login is ON. You will be asked for a 6-digit code when you log in.</p>
        ) : !setup ? (
          <>
            <p>Add a second step to your login: a 6-digit code from an app on your phone.</p>
            <button onClick={start}>Turn on two-step login</button>
          </>
        ) : (
          <form onSubmit={enable}>
            <p>1. Scan this QR code with Google Authenticator or Microsoft Authenticator:</p>
            <img
              className="qr"
              alt="QR code for the authenticator app"
              src={"data:image/svg+xml;utf8," + encodeURIComponent(setup.qr_svg)}
            />
            <p className="small muted">Or type this key: {setup.secret}</p>
            <label>
              2. Enter the 6-digit code shown in the app
              <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} />
            </label>
            {error && <p className="error">{error}</p>}
            <button type="submit">Turn on</button>
          </form>
        )}
      </div>
    </>
  );
}
