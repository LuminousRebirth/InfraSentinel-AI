import { api, jsonBody } from "./client";

export type RiskLevel = "low" | "medium" | "high";
export type AlertStatus = "pending_confirmation" | "assigned" | "processing" | "resolved" | "false_positive";

export interface Alert {
  id: string;
  event_id: string;
  project_id: string;
  owner_id: string;
  final_level: RiskLevel;
  status: AlertStatus;
  title_zh: string;
  title_en: string;
  summary: string | null;
  assignee_id: string | null;
  resolution_note: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface AlertDetail extends Alert {
  event: { class_name: string; observation_count: number; max_confidence: number; first_timestamp_ms: number; last_timestamp_ms: number };
  actions: Array<{ id: string; action: string; detail: string | null; created_at: string }>;
  attachments: Array<{ id: string; original_name: string; byte_size: number; created_at: string }>;
  analysis: Analysis | null;
}

export interface Analysis {
  id: string;
  status: "waiting_configuration" | "queued" | "running" | "succeeded" | "failed" | "cancelled";
  result_json: Record<string, unknown> | null;
  error_code: string | null;
}

export interface Provider {
  id: string;
  code: string;
  provider: "qwen" | "deepseek" | "glm";
  endpoint: string;
  model_name: string;
  supports_vision: boolean;
  timeout_seconds: number;
  max_retries: number;
  enabled: boolean;
  is_default: boolean;
}

export interface AlertRule {
  id: string;
  code: string;
  name_zh: string;
  name_en: string;
  project_id: string | null;
  class_name: string;
  min_confidence: number;
  risk_level: RiskLevel;
  merge_window_ms: number;
  iou_threshold: number;
  cooldown_seconds: number;
  priority: number;
  enabled: boolean;
}

export const getAlerts = () => api<Alert[]>("/alerts");
export const getAlert = (id: string) => api<AlertDetail>(`/alerts/${id}`);
export const getProviders = () => api<Provider[]>("/llm/providers");
export const getRules = () => api<AlertRule[]>("/admin/alert-rules");

export const updateAlert = (id: string, body: Record<string, unknown>) =>
  api<Alert>(`/alerts/${id}`, { method: "PATCH", body: jsonBody(body) });

export const analyzeAlert = (id: string, preferPersonal: boolean) =>
  api<Analysis>(`/alerts/${id}/analyze`, {
    method: "POST",
    body: jsonBody({ prefer_personal: preferPersonal }),
  });

export const createProvider = (body: Record<string, unknown>) =>
  api<Provider>("/admin/llm/providers", { method: "POST", body: jsonBody(body) });

export const createRule = (body: Record<string, unknown>) =>
  api<AlertRule>("/admin/alert-rules", { method: "POST", body: jsonBody(body) });

export const replaceRule = (rule: AlertRule, changes: Partial<AlertRule>) => {
  const value = { ...rule, ...changes };
  const body = {
    code: value.code, name_zh: value.name_zh, name_en: value.name_en,
    project_id: value.project_id, class_name: value.class_name,
    min_confidence: value.min_confidence, risk_level: value.risk_level,
    merge_window_ms: value.merge_window_ms, iou_threshold: value.iou_threshold,
    cooldown_seconds: value.cooldown_seconds, priority: value.priority, enabled: value.enabled,
  };
  return api<AlertRule>(`/admin/alert-rules/${rule.id}`, { method: "PUT", body: jsonBody(body) });
};

export const saveCredential = (providerId: string, apiKey: string, system: boolean) =>
  api<void>(
    system
      ? `/admin/llm/providers/${providerId}/credentials/system`
      : `/llm/providers/${providerId}/credentials/personal`,
    { method: "PUT", body: jsonBody({ api_key: apiKey }) },
  );

export const uploadAlertAttachment = (alertId: string, file: File) => {
  const body = new FormData();
  body.append("upload", file);
  return api<{ id: string }>(`/alerts/${alertId}/attachments`, { method: "POST", body });
};

export const deletePersonalCredential = (providerId: string) =>
  api<void>(`/llm/providers/${providerId}/credentials/personal`, { method: "DELETE" });
