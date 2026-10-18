import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

const HELP = {
  user: [
    ["/records", "My data", "Add personal data. It is stored encrypted."],
    ["/consents", "My permissions", "Give a company permission for a purpose, or withdraw it."],
    ["/log", "Activity log", "See every attempt to view your data, allowed or blocked."],
  ],
  company: [
    ["/consents", "Permissions given to us", "See which users allowed you to use which data."],
    ["/records", "Request data", "Ask for a user's data. You must give a purpose."],
    ["/log", "Activity log", "See every request you made and whether it was allowed."],
  ],
  investigator: [
    ["/forensics", "Forensics", "Run Carol's case study step by step: evidence copy, cover-up, comparison."],
    ["/alerts", "Alerts", "Suspicious activity found by four simple rules."],
    ["/cases", "Cases", "Collect log entries as evidence, write notes, download a PDF report."],
  ],
};

export default function Home({ user }) {
  const [cards, setCards] = useState([]);

  useEffect(() => {
    api("/summary").then((data) => setCards(data.cards)).catch(() => setCards([]));
  }, []);

  return (
    <>
      <h1>Welcome, {user.name}</h1>
      <p className="subtitle">Logged in as {user.role === "investigator" ? "an" : "a"} {user.role}.</p>

      <div className="stats">
        {cards.map(([label, value]) => (
          <div key={label} className="stat">
            <div className="stat-value">{value}</div>
            <div className="stat-label">{label}</div>
          </div>
        ))}
      </div>

      <h2>What you can do</h2>
      <div className="tiles">
        {HELP[user.role].map(([to, title, text]) => (
          <Link key={to} to={to} className="tile">
            <strong>{title}</strong>
            <span>{text}</span>
          </Link>
        ))}
      </div>

      <div className="card">
        <h2>Is the log safe?</h2>
        <p>
          Every log entry stores the SHA-256 hash of the entry before it, like links in a chain. If anyone edits or
          deletes an entry, the chain breaks. You can check it anytime on the <Link to="/log">Activity log</Link> page.
        </p>
      </div>
    </>
  );
}
