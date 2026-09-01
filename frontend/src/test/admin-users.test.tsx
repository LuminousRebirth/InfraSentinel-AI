import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { AdminUsersPage } from "../pages/AdminUsersPage";

const pendingUser = {
  id: "f3b0c4f1-5f8b-4bbc-a01a-1efb7cb5f416", email: "new@example.com", username: "new-user",
  display_name: "新用户", role: "user", status: "pending", locale: "zh-CN", rejection_reason: null,
  reviewed_at: null, last_login_at: null, created_at: "2026-09-01T00:00:00Z", projects: [],
};
function json(body: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })); }

test("administrator can approve a pending user", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/admin/users/") && init?.method === "PATCH") return json({ ...pendingUser, status: "enabled" });
    if (url.includes("/admin/users")) return json([pendingUser]);
    if (url.endsWith("/projects")) return json([]);
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<AdminUsersPage />);
  const operator = userEvent.setup();
  await operator.click(await screen.findByRole("button", { name: "批准" }));
  expect(fetch.mock.calls.some(([input, init]) => String(input).includes(pendingUser.id) && init?.method === "PATCH")).toBe(true);
});
