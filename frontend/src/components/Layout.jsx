import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";
import { humanize } from "../utils/format.js";

const NAV = {
  subject: [
    { section: "Privacy" },
    { to: "/consents", label: "My consents" },
    { to: "/records", label: "My protected records" },
    { section: "Accountability" },
    { to: "/audit", label: "Access history" },
    { to: "/integrity", label: "Audit integrity" },
  ],
  processor: [
    { section: "Data processing" },
    { to: "/consents", label: "Consents granted to me" },
    { to: "/records", label: "Request data access" },
    { section: "Accountability" },
    { to: "/audit", label: "My access log" },
    { to: "/integrity", label: "Audit integrity" },
  ],
  investigator: [
    { section: "Investigations" },
    { to: "/cases", label: "Cases" },
    { to: "/detection", label: "Detection rules" },
    { section: "Evidence" },
    { to: "/audit", label: "Audit trail" },
    { to: "/integrity", label: "Integrity verification" },
    { to: "/consents", label: "Consent registry" },
  ],
};

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);

  const needsMfa = user.role === "investigator" && !user.mfa_enabled;
  const items = needsMfa ? [] : NAV[user.role] ?? [];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className={`sidebar${open ? " open" : ""}`} aria-label="Main navigation">
        <Link className="brand" to="/">
          <img src="/shield.svg" alt="" />
          <div>
            <strong>ConsentGuard</strong>
            <span>Consent &amp; data access management</span>
          </div>
        </Link>
        <nav className="nav">
          {!needsMfa && <NavLink to="/" end>Dashboard</NavLink>}
          {items.map((item) =>
            item.section ? (
              <div key={item.section} className="nav-section">{item.section}</div>
            ) : (
              <NavLink key={item.to} to={item.to}>{item.label}</NavLink>
            ),
          )}
          <div className="nav-section">Account</div>
          <NavLink to="/account">Account security</NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="who">{user.display_name}</div>
          <div className="muted small">@{user.username} · {humanize(user.role)}</div>
          <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 10 }} onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <strong>ConsentGuard</strong>
          <button type="button" className="menu-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            Menu
          </button>
        </header>
        <main id="main" className="content" tabIndex={-1}>
          {needsMfa && (
            <div className="alert alert-warning" role="alert">
              <strong>MFA required.</strong> Investigator accounts must enable multi-factor authentication before
              accessing investigation features. Complete setup below.
            </div>
          )}
          <Outlet />
        </main>
        <p className="footer-note">
          ConsentGuard – Privacy-Centric User Consent and Data Access Management System · All data is synthetic ·
          Times shown in UTC
        </p>
      </div>
    </div>
  );
}
