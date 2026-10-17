import { useState } from "react";
import { toIsoFromLocalInput } from "../utils/format.js";

export const EMPTY_FILTERS = {
  start: "", end: "", actor_id: "", resource_id: "", action: "", consent_id: "", outcome: "", event_type: "",
};

// Filter form for audit events. Emits ISO timestamps (UTC) for the API.
export default function EventFilters({ onApply, compact = false }) {
  const [form, setForm] = useState(EMPTY_FILTERS);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    onApply({ ...form, start: toIsoFromLocalInput(form.start) ?? "", end: toIsoFromLocalInput(form.end) ?? "" });
  };
  const clear = () => {
    setForm(EMPTY_FILTERS);
    onApply(EMPTY_FILTERS);
  };

  return (
    <form className="form" onSubmit={submit} aria-label="Event filters">
      <div className="form-row">
        <div className="field">
          <label htmlFor="f-start">From (local time)</label>
          <input id="f-start" type="datetime-local" value={form.start} onChange={set("start")} />
        </div>
        <div className="field">
          <label htmlFor="f-end">To (local time)</label>
          <input id="f-end" type="datetime-local" value={form.end} onChange={set("end")} />
        </div>
        <div className="field">
          <label htmlFor="f-outcome">Outcome</label>
          <select id="f-outcome" value={form.outcome} onChange={set("outcome")}>
            <option value="">Any</option>
            {["allowed", "denied", "success", "failure", "info"].map((o) => <option key={o}>{o}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="f-type">Event type (prefix)</label>
          <input id="f-type" type="text" placeholder="e.g. record.access" value={form.event_type} onChange={set("event_type")} />
        </div>
      </div>
      {!compact && (
        <div className="form-row">
          <div className="field">
            <label htmlFor="f-actor">Actor ID</label>
            <input id="f-actor" type="number" min="1" value={form.actor_id} onChange={set("actor_id")} />
          </div>
          <div className="field">
            <label htmlFor="f-resource">Resource ID</label>
            <input id="f-resource" type="text" value={form.resource_id} onChange={set("resource_id")} />
          </div>
          <div className="field">
            <label htmlFor="f-action">Action</label>
            <input id="f-action" type="text" placeholder="e.g. read" value={form.action} onChange={set("action")} />
          </div>
          <div className="field">
            <label htmlFor="f-consent">Consent ID</label>
            <input id="f-consent" type="number" min="1" value={form.consent_id} onChange={set("consent_id")} />
          </div>
        </div>
      )}
      <div className="btn-row">
        <button className="btn" type="submit">Apply filters</button>
        <button className="btn btn-secondary" type="button" onClick={clear}>Clear</button>
      </div>
    </form>
  );
}
