import { Fragment, useState } from "react";
import { OutcomeBadge } from "./Badge.jsx";
import { formatTimestamp, personLabel } from "../utils/format.js";

// Audit events table with expandable integrity/detail rows and optional selection.
export default function EventTable({ events, selectable = false, selected, onToggle, actions }) {
  const [expanded, setExpanded] = useState(null);
  const columns = 7 + (selectable ? 1 : 0) + (actions ? 1 : 0);

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {selectable && <th scope="col"><span className="visually-hidden">Select</span></th>}
            <th scope="col">Seq</th>
            <th scope="col">Time (UTC)</th>
            <th scope="col">Event</th>
            <th scope="col">Actor</th>
            <th scope="col">Resource</th>
            <th scope="col">Outcome</th>
            <th scope="col">Reason</th>
            {actions && <th scope="col"><span className="visually-hidden">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <Fragment key={e.event_id}>
              <tr className={expanded === e.event_id ? "expanded-row" : undefined}>
                {selectable && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select event ${e.seq}`}
                      checked={selected.has(e.event_id)}
                      onChange={() => onToggle(e.event_id)}
                    />
                  </td>
                )}
                <td>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    aria-expanded={expanded === e.event_id}
                    aria-label={`Show details for event ${e.seq}`}
                    onClick={() => setExpanded(expanded === e.event_id ? null : e.event_id)}
                  >
                    #{e.seq}
                  </button>
                </td>
                <td className="nowrap">{formatTimestamp(e.timestamp)}</td>
                <td><code>{e.event_type}</code></td>
                <td>{e.actor_id ? personLabel(e.actor, e.actor_id) : <span className="muted">anonymous / system</span>}</td>
                <td>
                  {e.resource_type ? <span>{e.resource_type}</span> : "—"}
                  {e.resource_id && <div className="hash">{e.resource_id}</div>}
                </td>
                <td><OutcomeBadge outcome={e.outcome} /></td>
                <td className="small">{e.reason_code ?? "—"}</td>
                {actions && <td>{actions(e)}</td>}
              </tr>
              {expanded === e.event_id && (
                <tr className="expanded-row">
                  <td colSpan={columns}>
                    <dl className="dl small">
                      <dt>Event ID</dt><dd className="mono">{e.event_id}</dd>
                      <dt>Data subject</dt><dd>{personLabel(e.subject, e.subject_id)}</dd>
                      <dt>Action</dt><dd>{e.action ?? "—"}</dd>
                      <dt>Consent</dt><dd>{e.consent_id ? `#${e.consent_id}` : "—"}</dd>
                      <dt>Request ID</dt><dd className="mono">{e.request_id ?? "—"}</dd>
                      <dt>Details</dt><dd><code>{JSON.stringify(e.details)}</code></dd>
                      <dt>Previous hash</dt><dd className="hash">{e.prev_hash}</dd>
                      <dt>Event hash</dt><dd className="hash">{e.hash}</dd>
                    </dl>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
