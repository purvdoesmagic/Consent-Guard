import { humanize, outcomeTone, statusTone } from "../utils/format.js";

export function Badge({ tone = "neutral", children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({ status }) {
  return <Badge tone={statusTone(status)}>{humanize(status)}</Badge>;
}

export function OutcomeBadge({ outcome }) {
  return <Badge tone={outcomeTone(outcome)}>{outcome}</Badge>;
}

export function SeverityBadge({ severity }) {
  return <Badge tone={severity === "high" ? "danger" : severity === "medium" ? "warning" : "info"}>{severity}</Badge>;
}
