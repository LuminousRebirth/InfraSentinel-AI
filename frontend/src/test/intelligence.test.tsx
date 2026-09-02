import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { AlertsPage } from "../pages/AlertsPage";
import { AdminIntelligencePage } from "../pages/AdminIntelligencePage";

vi.mock("../auth/session", () => ({ useSession: () => ({ user: { role: "admin" } }) }));

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const alert = {
  id: "a1",
  event_id: "e1",
  project_id: "p1",
  owner_id: "u1",
  final_level: "medium",
  status: "pending_confirmation",
  title_zh: "管道裂缝预警",
  title_en: "Pipeline crack alert",
  summary: "CK · 82%",
  assignee_id: null,
  resolution_note: null,
  version: 1,
  created_at: "2026-09-02T00:00:00Z",
  updated_at: "2026-09-02T00:00:00Z",
};

test("alert center presents deterministic risk and queues advisory analysis", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.endsWith("/alerts") && !init?.method) return json([alert]);
    if (url.endsWith("/llm/providers")) return json([]);
    if (url.endsWith("/alerts/a1") && !init?.method) return json({ ...alert, event: { class_name: "CK", observation_count: 1, max_confidence: 0.82, first_timestamp_ms: 0, last_timestamp_ms: 0 }, actions: [], attachments: [], analysis: null });
    if (url.endsWith("/alerts/a1/analyze")) {
      return json({ id: "x1", status: "waiting_configuration", result_json: null, error_code: "llm.configuration_missing" });
    }
    throw new Error(`Unexpected request: ${String(input)}`);
  });
  render(<MemoryRouter><AlertsPage /></MemoryRouter>);
  expect(await screen.findAllByText("管道裂缝预警")).toHaveLength(2);
  await userEvent.setup().click(screen.getByRole("button", { name: "使用系统模型分析" }));
  expect(await screen.findByText("waiting_configuration")).toBeInTheDocument();
  expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/analyze"))).toBe(true);
});

test("admin credential is write-only", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.endsWith("/llm/providers") && !init?.method) return json([{ id: "provider-1", code: "qwen", provider: "qwen", endpoint: "https://example.com/v1", model_name: "vl", supports_vision: true, timeout_seconds: 60, max_retries: 2, enabled: true, is_default: true }]);
    if (url.endsWith("/admin/alert-rules")) return json([]);
    if (url.endsWith("/credentials/system")) return Promise.resolve(new Response(null, { status: 204 }));
    throw new Error(`Unexpected request: ${url}`);
  });
  render(<AdminIntelligencePage />);
  const key = await screen.findByLabelText("API Key");
  await userEvent.setup().type(key, "secret-key-value");
  await userEvent.setup().click(screen.getByRole("button", { name: "保存系统密钥" }));
  expect(await screen.findByText("系统密钥已加密保存")).toBeInTheDocument();
  expect(key).toHaveValue("");
  expect(fetch.mock.calls.some(([, init]) => String(init?.body).includes("secret-key-value"))).toBe(true);
});
