import { Link } from "react-router-dom";

const HELP = {
  user: [
    "Add your personal data under My data. It is stored encrypted.",
    "Give a company permission under My permissions, and withdraw it at any time.",
    "See every attempt to view your data in the Activity log.",
  ],
  company: [
    "See which users gave you permission under Permissions given to us.",
    "Request a user's data under Request data. You must say why (the purpose).",
    "You only get the data if the user's permission allows it. Every attempt is logged.",
  ],
  investigator: [
    "Alerts shows suspicious activity found in the log.",
    "Create a case, add log entries as evidence, write notes and download a PDF report.",
    "You can check the activity log, but you can never see personal data.",
  ],
};

export default function Home({ user }) {
  return (
    <>
      <h1>Welcome, {user.name}</h1>
      <div className="card">
        <h2>What you can do</h2>
        <ul>
          {HELP[user.role].map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h2>Is the log safe?</h2>
        <p>
          Every log entry is linked to the one before it with a SHA-256 hash. You can check anytime that nothing was
          changed on the <Link to="/log">Activity log</Link> page.
        </p>
      </div>
    </>
  );
}
