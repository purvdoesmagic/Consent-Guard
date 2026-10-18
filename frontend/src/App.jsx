import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api.js";
import Account from "./pages/Account.jsx";
import ActivityLog from "./pages/ActivityLog.jsx";
import Alerts from "./pages/Alerts.jsx";
import CaseDetail from "./pages/CaseDetail.jsx";
import Cases from "./pages/Cases.jsx";
import Consents from "./pages/Consents.jsx";
import Forensics from "./pages/Forensics.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import Records from "./pages/Records.jsx";
import Register from "./pages/Register.jsx";

// Menu links for each role. (The server also checks the role on every request.)
const MENU = {
  user: [
    ["/consents", "My permissions"],
    ["/records", "My data"],
    ["/log", "Activity log"],
  ],
  company: [
    ["/consents", "Permissions given to us"],
    ["/records", "Request data"],
    ["/log", "Activity log"],
  ],
  investigator: [
    ["/forensics", "Forensics"],
    ["/alerts", "Alerts"],
    ["/cases", "Cases"],
    ["/consents", "All permissions"],
    ["/log", "Activity log"],
  ],
};

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = still loading

  useEffect(() => {
    api("/me")
      .then((data) => setUser(data.user))
      .catch(() => setUser(null));
  }, []);

  async function logout() {
    await api("/logout", "POST");
    setUser(null);
  }

  if (user === undefined) return <p className="page">Loading...</p>;

  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Login onLogin={setUser} />} />
      </Routes>
    );
  }

  return (
    <div className="layout">
      <nav className="menu">
        <div className="brand">ConsentGuard</div>
        <NavLink to="/" end>Home</NavLink>
        {MENU[user.role].map(([to, label]) => (
          <NavLink key={to} to={to}>{label}</NavLink>
        ))}
        <NavLink to="/account">Account</NavLink>
        <div className="who">
          {user.name}
          <br />
          <small>{user.role}</small>
        </div>
        <button onClick={logout}>Log out</button>
      </nav>
      <main className="page">
        <Routes>
          <Route path="/" element={<Home user={user} />} />
          <Route path="/consents" element={<Consents user={user} />} />
          <Route path="/records" element={<Records user={user} />} />
          <Route path="/log" element={<ActivityLog />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:id" element={<CaseDetail />} />
          <Route path="/forensics" element={<Forensics />} />
          <Route path="/account" element={<Account user={user} onChange={setUser} />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
