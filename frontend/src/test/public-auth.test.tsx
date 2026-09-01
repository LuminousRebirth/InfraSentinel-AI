import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { App } from "../App";
import { SessionProvider } from "../auth/session";

const enabledUser = {
  id: "d7d73f88-ce1c-4d0b-8302-17d571c01db3",
  email: "operator@example.com",
  username: "operator",
  display_name: "巡检员",
  role: "user",
  status: "enabled",
  locale: "zh-CN",
  rejection_reason: null,
  reviewed_at: null,
  last_login_at: null,
  created_at: "2026-09-01T00:00:00Z",
  projects: [],
};

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

test("anonymous operator can sign in and reach the inspection desk", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.endsWith("/auth/me")) return response({ error: { code: "auth.required", message: "请先登录" } }, 401);
    if (url.endsWith("/auth/login")) return response(enabledUser);
    throw new Error(`Unexpected request: ${url}`);
  });
  render(<MemoryRouter initialEntries={["/login"]}><SessionProvider><App /></SessionProvider></MemoryRouter>);
  const operator = userEvent.setup();
  await operator.type(await screen.findByLabelText("邮箱或用户名"), "operator");
  await operator.type(screen.getByLabelText("密码"), "correct horse battery staple");
  await operator.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByRole("heading", { name: "值守概览" })).toBeInTheDocument();
});

test("language switch updates public controls", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => response({}, 401));
  render(<MemoryRouter initialEntries={["/login"]}><SessionProvider><App /></SessionProvider></MemoryRouter>);
  const operator = userEvent.setup();
  await operator.click(await screen.findByRole("button", { name: "语言" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument());
});

test("pending account is kept outside the authenticated workspace", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ ...enabledUser, status: "pending" }));
  render(<MemoryRouter initialEntries={["/app"]}><SessionProvider><App /></SessionProvider></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "账户正在等待审核" })).toBeInTheDocument();
});

test("normal user cannot enter administrator routes", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => response(enabledUser));
  render(<MemoryRouter initialEntries={["/admin/users"]}><SessionProvider><App /></SessionProvider></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "值守概览" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "用户与权限" })).not.toBeInTheDocument();
});
