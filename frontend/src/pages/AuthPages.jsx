import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Alert, ErrorAlert } from "../components/Feedback.jsx";
import { useAction } from "../hooks/useApi.js";
import { useAuth } from "../hooks/useAuth.jsx";
import { api } from "../services/api.js";

function AuthCard({ title, children }) {
  return (
    <div className="auth-page">
      <main className="auth-card">
        <div className="brand-row">
          <img src="/shield.svg" alt="" />
          <h1>{title}</h1>
        </div>
        <p className="tagline">ConsentGuard – Privacy-Centric User Consent and Data Access Management System</p>
        {children}
      </main>
    </div>
  );
}

export function LoginPage() {
  const { status, login, notice } = useAuth();
  const [form, setForm] = useState({ username: "", password: "" });
  const action = useAction();
  const navigate = useNavigate();
  const location = useLocation();

  if (status === "authenticated") return <Navigate to="/" replace />;
  if (status === "mfa") return <Navigate to="/mfa" replace />;

  const submit = async (e) => {
    e.preventDefault();
    const result = await action.run(() => login(form.username, form.password));
    if (result) navigate(result.mfa_required ? "/mfa" : "/", { replace: true });
  };

  return (
    <AuthCard title="Sign in">
      {location.state?.registered && <Alert tone="success">Account created. You can now sign in.</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}
      <ErrorAlert error={action.error} />
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="username">Username</label>
          <input id="username" type="text" autoComplete="username" required value={form.username}
                 onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        <button className="btn" type="submit" disabled={action.pending}>
          {action.pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="small muted" style={{ marginTop: 16 }}>
        No account? <Link to="/register">Create one</Link>
      </p>
    </AuthCard>
  );
}

export function RegisterPage() {
  const { status } = useAuth();
  const [form, setForm] = useState({ username: "", display_name: "", password: "", confirm: "", role: "subject" });
  const action = useAction();
  const navigate = useNavigate();
  const [clientError, setClientError] = useState(null);

  if (status === "authenticated") return <Navigate to="/" replace />;
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setClientError(null);
    if (form.password !== form.confirm) {
      setClientError("Passwords do not match.");
      return;
    }
    const { confirm: _unused, ...body } = form;
    const result = await action.run(() => api("/auth/register", { method: "POST", body }));
    if (result) navigate("/login", { replace: true, state: { registered: true } });
  };

  return (
    <AuthCard title="Create account">
      <Alert tone="warning">Demonstration system: use synthetic details only.</Alert>
      {clientError && <Alert tone="error">{clientError}</Alert>}
      <ErrorAlert error={action.error} />
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="r-username">Username</label>
          <input id="r-username" type="text" autoComplete="username" required minLength={3} maxLength={32}
                 value={form.username} onChange={set("username")} />
          <span className="help">3–32 characters: letters, digits, dot, dash or underscore.</span>
        </div>
        <div className="field">
          <label htmlFor="r-display">Display name</label>
          <input id="r-display" type="text" required maxLength={80} value={form.display_name} onChange={set("display_name")} />
        </div>
        <fieldset>
          <legend>Account type</legend>
          <div className="checkbox-group">
            <label className="checkbox">
              <input type="radio" name="role" value="subject" checked={form.role === "subject"} onChange={set("role")} />
              Data subject (I own data and grant consent)
            </label>
            <label className="checkbox">
              <input type="radio" name="role" value="processor" checked={form.role === "processor"} onChange={set("role")} />
              Data processor (I request access under consent)
            </label>
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor="r-password">Password</label>
          <input id="r-password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}
                 value={form.password} onChange={set("password")} aria-describedby="pw-help" />
          <span id="pw-help" className="help">At least 12 characters using three of: lowercase, uppercase, digits, symbols.</span>
        </div>
        <div className="field">
          <label htmlFor="r-confirm">Confirm password</label>
          <input id="r-confirm" type="password" autoComplete="new-password" required value={form.confirm} onChange={set("confirm")} />
        </div>
        <button className="btn" type="submit" disabled={action.pending}>
          {action.pending ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="small muted" style={{ marginTop: 16 }}>
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </AuthCard>
  );
}

export function MfaVerifyPage() {
  const { status, verifyMfa, logout } = useAuth();
  const [useRecovery, setUseRecovery] = useState(false);
  const [value, setValue] = useState("");
  const action = useAction();
  const navigate = useNavigate();

  if (status === "authenticated") return <Navigate to="/" replace />;
  if (status === "anonymous") return <Navigate to="/login" replace />;

  const submit = async (e) => {
    e.preventDefault();
    const payload = useRecovery ? { recovery_code: value.trim() } : { code: value.trim() };
    await action.run(() => verifyMfa(payload));
  };

  return (
    <AuthCard title="Two-step verification">
      <p className="small">
        {useRecovery
          ? "Enter one of your single-use recovery codes."
          : "Enter the 6-digit code from your authenticator app."}
      </p>
      <ErrorAlert error={action.error} />
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="mfa-code">{useRecovery ? "Recovery code" : "Verification code"}</label>
          <input
            id="mfa-code"
            type="text"
            className={useRecovery ? undefined : "code-input"}
            inputMode={useRecovery ? "text" : "numeric"}
            autoComplete="one-time-code"
            pattern={useRecovery ? undefined : "\\d{6}"}
            maxLength={useRecovery ? 20 : 6}
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </div>
        <button className="btn" type="submit" disabled={action.pending}>
          {action.pending ? "Verifying…" : "Verify"}
        </button>
      </form>
      <div className="btn-row" style={{ marginTop: 14 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setUseRecovery(!useRecovery); setValue(""); }}>
          {useRecovery ? "Use authenticator code" : "Use a recovery code"}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={async () => { await logout(); navigate("/login"); }}>
          Cancel sign-in
        </button>
      </div>
    </AuthCard>
  );
}
