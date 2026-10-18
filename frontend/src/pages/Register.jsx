import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function Register() {
  const [form, setForm] = useState({ username: "", name: "", password: "", role: "user" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  function change(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/register", "POST", form);
      setDone(true);
    } catch (err) {
      setError(err.message);
    }
  }

  if (done) {
    return (
      <div className="login-box">
        <h1>Account created</h1>
        <p>
          You can now <Link to="/">log in</Link>.
        </p>
      </div>
    );
  }

  return (
    <div className="login-box">
      <h1>Register</h1>
      <form onSubmit={submit}>
        <label>
          Username
          <input name="username" value={form.username} onChange={change} required />
        </label>
        <label>
          Your name (or company name)
          <input name="name" value={form.name} onChange={change} required />
        </label>
        <label>
          Password (at least 8 characters)
          <input name="password" type="password" value={form.password} onChange={change} required />
        </label>
        <label>
          I am a
          <select name="role" value={form.role} onChange={change}>
            <option value="user">User (I own personal data)</option>
            <option value="company">Company (I want to use data)</option>
          </select>
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit">Create account</button>
      </form>
      <p>
        Already registered? <Link to="/">Log in</Link>
      </p>
    </div>
  );
}
