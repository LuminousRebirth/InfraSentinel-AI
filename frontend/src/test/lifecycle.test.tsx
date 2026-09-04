import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AdminLifecyclePage } from "../pages/AdminLifecyclePage";
import { setLocale } from "../i18n";

function json(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

test("lifecycle workbench shows dataset provenance and samples", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.endsWith("/datasets") && init?.method === "POST") return json({ id: "d2", project_id: "p1", owner_id: "u1", name: "New set", description: null, status: "active", versions: [] });
    if (url.endsWith("/datasets")) return json([{ id: "d1", project_id: "p1", owner_id: "u1", name: "东区管廊", description: null, status: "active", versions: [{ id: "v1", dataset_id: "d1", version_number: 1, status: "draft", source: "upload", train_ratio: 80, val_ratio: 10, test_ratio: 10, sample_count: 1, annotation_count: 1, byte_size: 200, revision: 2 }] }]);
    if (url.endsWith("/projects")) return json([{ id: "p1", code: "EAST", name: "东区", status: "active" }]);
    if (url.endsWith("/dataset-categories")) return json([{ id: "c1", code: "CK", name_zh: "管道裂缝", name_en: "Pipeline crack", color: "#ef4444", enabled: true }]);
    if (url.endsWith("/lifecycle-jobs") || url.endsWith("/managed-models") || url.endsWith("/model-deployments")) return json([]);
    if (url.includes("/dataset-versions/v1/samples")) return json([{ id: "s1", version_id: "v1", original_name: "frame-001.jpg", mime_type: "image/jpeg", byte_size: 200, sha256: "1".repeat(64), width: 640, height: 480, split: "train", review_status: "unreviewed", duplicate_group: null, revision: 1, annotations: [{ id: "a1", category_id: "c1", cx: .5, cy: .5, width: .2, height: .2 }] }]);
    throw new Error(`Unexpected request: ${url}`);
  });
  render(<AdminLifecyclePage />);
  expect(await screen.findByText("东区管廊")).toBeInTheDocument();
  expect(await screen.findAllByText("frame-001.jpg")).toHaveLength(2);
  expect(screen.getByText("数据与模型工坊")).toBeInTheDocument();
  expect(screen.getByText("80 / 10 / 10")).toBeInTheDocument();
  const canvas = screen.getByLabelText("标注画布");
  vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100,
    toJSON: () => ({}),
  });
  fireEvent.pointerDown(canvas, { clientX: 10, clientY: 20 });
  fireEvent.pointerUp(canvas, { clientX: 40, clientY: 60 });
  expect(screen.getAllByRole("button", { name: "×" })).toHaveLength(2);
  act(() => setLocale("en"));
  expect(screen.getByText("Data & model workshop")).toBeInTheDocument();
  expect(screen.getByLabelText("Annotation canvas")).toBeInTheDocument();
  act(() => setLocale("zh-CN"));
  const datasetName = screen.getByPlaceholderText("例如：东区管廊九月巡检");
  fireEvent.change(datasetName, { target: { value: "New set" } });
  fireEvent.click(screen.getByRole("button", { name: "新建数据集" }));
  await screen.findByText("数据集已创建");
  expect(datasetName).toHaveValue("");
});
