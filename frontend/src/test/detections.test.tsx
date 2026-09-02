import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { DetectionHistoryPage } from "../pages/DetectionHistoryPage";
import { DetectionPage } from "../pages/DetectionPage";

function json(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
}

test("detection create screen exposes available local model", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.endsWith("/projects")) return json([{ id: "p1", code: "P1", name: "Plant", status: "active" }]);
    if (url.endsWith("/vision/models")) return json([{ id: "m1", code: "pipeline-local", name_zh: "管道缺陷模型", name_en: "Pipeline", scene: "pipeline", classes_json: ["CK"], input_size: 640, preferred_backend: "auto", availability: "available", unavailable_reason: null, version_label: "abc123", engine_configured: true }]);
    throw new Error(`Unexpected request: ${url}`);
  });
  render(<MemoryRouter><DetectionPage /></MemoryRouter>);
  expect(await screen.findByRole("option", { name: /管道缺陷模型/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交检测" })).toBeDisabled();
});

test("history shows durable job status and detail link", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json([{ id: "job-1", kind: "image", status: "succeeded", project_id: "p1", owner_id: "u1", model_id: "m1", scene: "pipeline", parameters_json: {}, result_json: {}, progress_percent: 100, progress_detail: "completed", attempt: 1, max_attempts: 3, retry_of_id: null, error_code: null, error_detail: null, queued_at: "2026-09-02T00:00:00Z", started_at: "2026-09-02T00:00:01Z", finished_at: "2026-09-02T00:00:02Z", created_at: "2026-09-02T00:00:00Z", media: [], observations: [], metrics: [] }]));
  render(<MemoryRouter><DetectionHistoryPage /></MemoryRouter>);
  expect(await screen.findByText("已完成")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看详情" })).toHaveAttribute("href", "/detections/job-1");
});
