import { SeverityBadge } from "./Badge.jsx";
import { EmptyState } from "./Feedback.jsx";
import { formatTimestamp } from "../utils/format.js";

// Renders system-generated indicators with their rule, explanation and evidence.
export default function IndicatorList({ indicators, renderActions }) {
  if (!indicators.length) {
    return (
      <EmptyState title="No indicators">
        <p>No detection rule was triggered by the examined events.</p>
      </EmptyState>
    );
  }
  return (
    <div>
      <p className="muted small">
        Indicators are produced by transparent rules. They are leads for an investigator to assess, not proof of
        malicious activity.
      </p>
      {indicators.map((ind, i) => (
        <article key={`${ind.rule_id}-${ind.first_seen}-${i}`} className={`indicator ${ind.severity}`}>
          <div className="card-header" style={{ marginBottom: 6 }}>
            <h3>
              <code>{ind.rule_id}</code> {ind.title}
            </h3>
            <SeverityBadge severity={ind.severity} />
          </div>
          <p>{ind.explanation}</p>
          <p className="meta">
            Rule {ind.rule_code} · {ind.event_count} supporting event(s) · {formatTimestamp(ind.first_seen)} →{" "}
            {formatTimestamp(ind.last_seen)}
          </p>
          <details>
            <summary className="small">Supporting evidence</summary>
            <ul className="small">
              {ind.supporting_events.map((e) => (
                <li key={e.event_id}>
                  #{e.seq} · {formatTimestamp(e.timestamp)} · <code>{e.event_type}</code> · {e.reason_code ?? "—"} ·{" "}
                  <span className="mono">{e.event_id}</span>
                </li>
              ))}
            </ul>
          </details>
          {renderActions && <div style={{ marginTop: 10 }}>{renderActions(ind)}</div>}
        </article>
      ))}
    </div>
  );
}
