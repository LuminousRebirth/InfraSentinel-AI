import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { AdminAuditPage } from "../pages/AdminAuditPage";

test("audit page renders sanitized change details", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([{
    id: "48bdf770-673f-4fc6-a34c-6baf034347bd", actor_id: null, source_ip: "127.0.0.1",
    action: "admin.user_status", target_type: "user", target_id: "4b8da0cf-b878-4fa4-88cd-69964a19590b",
    before_state: { status: "pending" }, after_state: { status: "enabled" }, result: "success",
    detail: null, created_at: "2026-09-01T00:00:00Z",
  }]), { status: 200, headers: { "Content-Type": "application/json" } }));
  render(<AdminAuditPage />);
  expect(await screen.findByText("admin.user_status")).toBeInTheDocument();
  await userEvent.setup().click(screen.getByText("变更详情"));
  expect(screen.getByText(/"pending"/)).toBeInTheDocument();
  expect(screen.getByText(/"enabled"/)).toBeInTheDocument();
});
