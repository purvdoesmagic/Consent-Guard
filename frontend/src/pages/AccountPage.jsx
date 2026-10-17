import { useState } from "react";
import { Badge } from "../components/Badge.jsx";
import { Alert, AsyncBlock, ErrorAlert } from "../components/Feedback.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { api } from "../services/api.js";
import { formatTimestamp, humanize } from "../utils/format.js";

function RecoveryCodes({ codes }) {
  return (
    <div>
      <Alert tone="warning">
        <strong>Save these recovery codes now.</strong> Each code works once and they will not be shown again.
      </Alert>
      <div className="codes" aria-label="Recovery codes">
        {codes.map((c) => <span key={c}>{c}</span>)}
      </div>
    </div>
  );
}

function MfaSection() {
  const { user, refresh } = useAuth();
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState(null);
  const [reauth, setReauth] = useState({ password: "", code: "" });
  const action = useAction();

  const start = async () => {
    const result = await action.run(() => api("/auth/mfa/setup", { method: "POST" }));
    if (result) { setSetup(result); setCodes(null); }
  };
  const enable = async (e) => {
    e.preventDefault();
    const result = await action.run(() => api("/auth/mfa/enable", { method: "POST", body: { code } }), "Multi-factor authentication enabled.");
    if (result) { setCodes(result.recovery_codes); setSetup(null); setCode(""); refresh(); }
  };
  const disable = async (e) => {
    e.preventDefault();
    if (!window.confirm("Disable MFA? Your account will be protected by password only.")) return;
    const result = await action.run(() => api("/auth/mfa/disable", { method: "POST", body: reauth }), "MFA disabled.");
    if (result) { setReauth({ password: "", code: "" }); setCodes(null); refresh(); }
  };
  const regenerate = async (e) => {
    e.preventDefault();
    const result = await action.run(() => api("/auth/mfa/recovery-codes", { method: "POST", body: reauth }), "New recovery codes issued; old codes no longer work.");
    if (result) { setCodes(result.recovery_codes); setReauth({ password: "", code: "" }); refresh(); }
  };

  return (
    <section className="card">
      <div className="card-header">
        <h2>Multi-factor authentication (TOTP)</h2>
        <Badge tone={user.mfa_enabled ? "success" : "warning"}>{user.mfa_enabled ? "Enabled" : "Not enabled"}</Badge>
      </div>
      <Alert tone="success">{action.success}</Alert>
      <ErrorAlert error={action.error} />
      {codes && <RecoveryCodes codes={codes} />}

      {!user.mfa_enabled && !setup && (
        <>
          <p>Protect your account with a 6-digit code from an authenticator app (Microsoft Authenticator, Google Authenticator, Aegis, etc.).</p>
          <button type="button" className="btn" onClick={start} disabled={action.pending}>Set up MFA</button>
        </>
      )}

      {setup && (
        <div className="grid grid-2">
          <div>
            <h3>1. Scan the QR code</h3>
            <img className="qr" src={setup.qr_svg_data_uri} alt="QR code containing the TOTP enrollment secret" />
            <p className="small">Cannot scan? Enter this key manually (time-based, 6 digits, 30 seconds):</p>
            <p className="mono break">{setup.secret}</p>
          </div>
          <form className="form" onSubmit={enable}>
            <h3>2. Confirm with a code</h3>
            <div className="field">
              <label htmlFor="mfa-enable-code">Code from your app</label>
              <input id="mfa-enable-code" className="code-input" type="text" inputMode="numeric" pattern="\d{6}" maxLength={6}
                     autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} />
            </div>
            <div className="btn-row">
              <button className="btn" type="submit" disabled={action.pending}>Enable MFA</button>
              <button className="btn btn-secondary" type="button" onClick={() => setSetup(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {user.mfa_enabled && (
        <>
          <p className="small">Recovery codes remaining: <strong>{user.recovery_codes_remaining}</strong></p>
          <form className="form" onSubmit={(e) => e.preventDefault()}>
            <p className="small muted">Confirm your identity to manage MFA.</p>
            <div className="form-row">
              <div className="field">
                <label htmlFor="re-pass">Current password</label>
                <input id="re-pass" type="password" autoComplete="current-password" value={reauth.password}
                       onChange={(e) => setReauth({ ...reauth, password: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="re-code">Authenticator code</label>
                <input id="re-code" type="text" inputMode="numeric" maxLength={6} autoComplete="one-time-code" value={reauth.code}
                       onChange={(e) => setReauth({ ...reauth, code: e.target.value })} />
              </div>
            </div>
            <div className="btn-row">
              <button className="btn btn-secondary" type="button" onClick={regenerate} disabled={action.pending}>Regenerate recovery codes</button>
              <button className="btn btn-danger" type="button" onClick={disable} disabled={action.pending}>Disable MFA</button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}

function PasswordSection() {
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [mismatch, setMismatch] = useState(false);
  const action = useAction();
  const submit = async (e) => {
    e.preventDefault();
    setMismatch(form.new_password !== form.confirm);
    if (form.new_password !== form.confirm) return;
    const result = await action.run(() => api("/auth/password", {
      method: "POST", body: { current_password: form.current_password, new_password: form.new_password },
    }));
    if (result) {
      setForm({ current_password: "", new_password: "", confirm: "" });
      action.reset();
      window.alert(`Password changed. ${result.sessions_revoked} other session(s) were signed out.`);
    }
  };
  return (
    <section className="card">
      <h2>Change password</h2>
      {mismatch && <Alert tone="error">New passwords do not match.</Alert>}
      <ErrorAlert error={action.error} />
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="pw-current">Current password</label>
          <input id="pw-current" type="password" autoComplete="current-password" required value={form.current_password}
                 onChange={(e) => setForm({ ...form, current_password: e.target.value })} />
        </div>
        <div className="form-row">
          <div className="field">
            <label htmlFor="pw-new">New password</label>
            <input id="pw-new" type="password" autoComplete="new-password" required minLength={12} value={form.new_password}
                   onChange={(e) => setForm({ ...form, new_password: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="pw-confirm">Confirm new password</label>
            <input id="pw-confirm" type="password" autoComplete="new-password" required value={form.confirm}
                   onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
          </div>
        </div>
        <div><button className="btn" type="submit" disabled={action.pending}>Change password</button></div>
      </form>
    </section>
  );
}

function SessionsSection() {
  const state = useApi("/auth/sessions");
  const action = useAction();
  const revoke = async () => {
    const result = await action.run(() => api("/auth/sessions/revoke-others", { method: "POST" }));
    if (result) state.reload();
  };
  return (
    <section className="card">
      <div className="card-header">
        <h2>Active sessions</h2>
        <button type="button" className="btn btn-secondary btn-sm" onClick={revoke} disabled={action.pending}>Sign out other sessions</button>
      </div>
      <ErrorAlert error={action.error} />
      <AsyncBlock state={state}>
        {(d) => (
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">Started</th><th scope="col">Last active</th><th scope="col">Expires</th><th scope="col">MFA</th><th scope="col">Client</th></tr></thead>
              <tbody>
                {d.sessions.map((s) => (
                  <tr key={s.id}>
                    <td className="nowrap">{formatTimestamp(s.created_at)} {s.current && <Badge tone="primary">this session</Badge>}</td>
                    <td className="nowrap">{formatTimestamp(s.last_seen_at)}</td>
                    <td className="nowrap">{formatTimestamp(s.expires_at)}</td>
                    <td>{s.mfa_verified ? "Yes" : "No"}</td>
                    <td className="small">{s.user_agent || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncBlock>
    </section>
  );
}

export default function AccountPage() {
  const { user } = useAuth();
  return (
    <>
      <div className="page-header">
        <div>
          <h1>Account security</h1>
          <p>Manage multi-factor authentication, your password and active sessions.</p>
        </div>
      </div>
      <section className="card">
        <dl className="dl">
          <dt>Username</dt><dd>{user.username}</dd>
          <dt>Display name</dt><dd>{user.display_name}</dd>
          <dt>Role</dt><dd>{humanize(user.role)}</dd>
          <dt>Member since</dt><dd>{formatTimestamp(user.created_at)}</dd>
        </dl>
      </section>
      <MfaSection />
      <PasswordSection />
      <SessionsSection />
    </>
  );
}
