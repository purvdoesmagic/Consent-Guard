import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EventTable from "../components/EventTable.jsx";
import IndicatorList from "../components/IndicatorList.jsx";

const event = {
  seq: 7, event_id: "11111111-2222-3333-4444-555555555555", timestamp: "2026-10-17T06:54:29.000000Z",
  event_type: "record.access", actor_id: 2, actor: { username: "acme", display_name: "Acme", role: "processor" },
  subject_id: 1, subject: { username: "alice", display_name: "Alice", role: "subject" },
  resource_type: "record", resource_id: "abc", action: "read", outcome: "denied",
  reason_code: "DENY_CONSENT_WITHDRAWN", consent_id: 3, request_id: "r1", details: { purpose: "marketing" },
  prev_hash: "a".repeat(64), hash: "b".repeat(64),
};

describe("EventTable", () => {
  it("renders events and reveals hash-chain fields on demand", async () => {
    render(<EventTable events={[event]} />);
    expect(screen.getByText("record.access")).toBeInTheDocument();
    expect(screen.getByText("Acme (acme)")).toBeInTheDocument();
    expect(screen.getByText("denied")).toBeInTheDocument();
    expect(screen.queryByText("b".repeat(64))).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show details for event 7/i }));
    expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
    expect(screen.getByText(event.event_id)).toBeInTheDocument();
  });

  it("supports selection for case linking", async () => {
    const onToggle = vi.fn();
    render(<EventTable events={[event]} selectable selected={new Set()} onToggle={onToggle} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /select event 7/i }));
    expect(onToggle).toHaveBeenCalledWith(event.event_id);
  });
});

describe("IndicatorList", () => {
  it("shows an empty state", () => {
    render(<IndicatorList indicators={[]} />);
    expect(screen.getByText("No indicators")).toBeInTheDocument();
  });

  it("explains indicators and states they are not proof", () => {
    render(<IndicatorList indicators={[{
      rule_id: "R2", rule_code: "ACCESS_AFTER_WITHDRAWAL", title: "Access attempted after consent withdrawal",
      severity: "high", explanation: "Explanation text", event_count: 1, event_ids: [event.event_id],
      first_seen: event.timestamp, last_seen: event.timestamp,
      supporting_events: [{ event_id: event.event_id, seq: 7, timestamp: event.timestamp, event_type: "record.access", reason_code: "DENY_CONSENT_WITHDRAWN" }],
    }]} />);
    expect(screen.getByText(/not proof of malicious activity/i)).toBeInTheDocument();
    expect(screen.getByText("Explanation text")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });
});
