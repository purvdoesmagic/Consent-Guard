import { describe, expect, it } from "vitest";
import { formatTimestamp, humanize, personLabel, statusTone, toIsoFromLocalInput } from "../utils/format.js";

describe("format helpers", () => {
  it("formats timestamps consistently in UTC", () => {
    expect(formatTimestamp("2026-10-17T06:54:29.123456Z")).toBe("2026-10-17 06:54:29 UTC");
    expect(formatTimestamp("2026-10-17T06:54:29Z", { seconds: false })).toBe("2026-10-17 06:54 UTC");
    expect(formatTimestamp(null)).toBe("—");
  });

  it("converts datetime-local input to an ISO UTC string", () => {
    // Independent of the machine's timezone (including half-hour offsets).
    const iso = toIsoFromLocalInput("2026-10-17T12:30");
    expect(iso).toBe(new Date(2026, 9, 17, 12, 30).toISOString());
    expect(iso.endsWith("Z")).toBe(true);
    expect(toIsoFromLocalInput("")).toBeNull();
  });

  it("humanizes codes and labels people", () => {
    expect(humanize("under_review")).toBe("Under review");
    expect(personLabel({ display_name: "Alice", username: "alice" })).toBe("Alice (alice)");
    expect(personLabel(null, 4)).toBe("User #4");
    expect(statusTone("withdrawn")).toBe("danger");
  });
});
