import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { StatusBadge } from "../components/Badge.jsx";
import { AsyncBlock, EmptyState, ErrorAlert } from "../components/Feedback.jsx";
import { useAction, useApi } from "../hooks/useApi.js";
import { api } from "../services/api.js";
import { formatTimestamp, toIsoFromLocalInput } from "../utils/format.js";

export default function CasesPage() {
  const state = useApi("/cases");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", scope_start: "", scope_end: "" });
  const action = useAction();
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    const body = {
      title: form.title,
      description: form.description,
      scope_start: toIsoFromLocalInput(form.scope_start) ?? undefined,
      scope_end: toIsoFromLocalInput(form.scope_end) ?? undefined,
    };
    const result = await action.run(() => api("/cases", { method: "POST", body }));
    if (result) navigate(`/cases/${result.case.id}`);
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Investigation cases</h1>
          <p>Cases you lead. Each case collects evidence events, notes, findings and a downloadable report.</p>
        </div>
        <button type="button" className="btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Close form" : "New case"}
        </button>
      </div>
      {showForm && (
        <section className="card">
          <h2>Open a new case</h2>
          <ErrorAlert error={action.error} />
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="case-title">Title</label>
              <input id="case-title" type="text" required minLength={3} maxLength={150} value={form.title}
                     onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="case-desc">Description</label>
              <textarea id="case-desc" maxLength={4000} value={form.description}
                        onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="case-start">Scope start (optional)</label>
                <input id="case-start" type="datetime-local" value={form.scope_start}
                       onChange={(e) => setForm({ ...form, scope_start: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="case-end">Scope end (optional)</label>
                <input id="case-end" type="datetime-local" value={form.scope_end}
                       onChange={(e) => setForm({ ...form, scope_end: e.target.value })} />
              </div>
            </div>
            <div><button className="btn" type="submit" disabled={action.pending}>Create case</button></div>
          </form>
        </section>
      )}
      <section className="card">
        <AsyncBlock state={state} isEmpty={(d) => d.cases.length === 0}
                    empty={<EmptyState title="No cases yet"><p>Open a case to begin an investigation.</p></EmptyState>}>
          {(d) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Case</th><th scope="col">Title</th><th scope="col">Status</th>
                    <th scope="col">Evidence</th><th scope="col">Notes</th><th scope="col">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {d.cases.map((c) => (
                    <tr key={c.id}>
                      <td className="nowrap"><Link to={`/cases/${c.id}`}>{c.case_number}</Link></td>
                      <td>{c.title}</td>
                      <td><StatusBadge status={c.status} /></td>
                      <td>{c.linked_event_count}</td>
                      <td>{c.note_count}</td>
                      <td className="nowrap">{formatTimestamp(c.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBlock>
      </section>
    </>
  );
}
