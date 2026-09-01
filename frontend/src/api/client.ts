export type Locale = "zh-CN" | "en";
export type UserRole = "admin" | "user";
export type UserStatus = "pending" | "enabled" | "disabled" | "rejected";

export interface Project {
  id: string;
  code: string;
  name: string;
  status: "active" | "disabled";
}

export interface User {
  id: string;
  email: string;
  username: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
  locale: Locale;
  rejection_reason: string | null;
  reviewed_at: string | null;
  last_login_at: string | null;
  created_at: string;
  projects: Project[];
}

export interface AuditEvent {
  id: string;
  actor_id: string | null;
  source_ip: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  result: "success" | "failure";
  detail: string | null;
  created_at: string;
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; fields?: ErrorField[] | null };
}

export interface ErrorField {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly fields: ErrorField[] = [],
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Accept-Language", localStorage.getItem("infrasentinel.locale") ?? "zh-CN");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new ApiError(
      response.status,
      payload.error?.code ?? "request.failed",
      payload.error?.message ?? `Request failed (${response.status})`,
      payload.error?.fields ?? [],
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const jsonBody = (value: unknown): string => JSON.stringify(value);
