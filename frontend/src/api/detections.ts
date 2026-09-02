import { ApiError, api, jsonBody, type Project } from "./client";

export type DetectionKind = "image" | "video" | "obs";
export type JobStatus = "queued" | "running" | "cancelling" | "cancelled" | "succeeded" | "failed";

export interface VisionModel {
  id: string;
  code: string;
  name_zh: string;
  name_en: string;
  scene: "pipeline" | "ppe";
  classes_json: string[];
  input_size: number;
  preferred_backend: "auto" | "trt" | "pt";
  availability: "available" | "unavailable";
  unavailable_reason: string | null;
  version_label: string;
  engine_configured: boolean;
}

export interface DetectionMedia {
  id: string;
  role: "original" | "annotated" | "keyframe";
  media_type: "image" | "video";
  original_name: string;
  mime_type: string;
  byte_size: number;
  sha256: string;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  fps: number | null;
  frame_count: number | null;
}

export interface DetectionObservation {
  id: string;
  frame_index: number;
  timestamp_ms: number;
  class_name: string;
  confidence: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  inference_ms: number;
}

export interface DetectionJob {
  id: string;
  kind: DetectionKind;
  status: JobStatus;
  project_id: string;
  owner_id: string;
  model_id: string;
  scene: "pipeline" | "ppe";
  parameters_json: Record<string, unknown>;
  result_json: Record<string, unknown> | null;
  progress_percent: number;
  progress_detail: string | null;
  attempt: number;
  max_attempts: number;
  retry_of_id: string | null;
  error_code: string | null;
  error_detail: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  media: DetectionMedia[];
  observations: DetectionObservation[];
  metrics: Array<Record<string, number | string | null>>;
}

export interface DetectionParameters {
  confidence: number;
  iou: number;
  input_size?: number;
  device?: "auto" | "cuda:0" | "cpu";
  detection_fps?: number;
  resolution?: "640p" | "720p";
}

async function formRequest<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    body: form,
    credentials: "same-origin",
    headers: { "Accept-Language": localStorage.getItem("infrasentinel.locale") ?? "zh-CN" },
  });
  const payload = (await response.json().catch(() => ({}))) as T & {
    error?: { code?: string; message?: string };
  };
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload.error?.code ?? "request.failed",
      payload.error?.message ?? `Request failed (${response.status})`,
    );
  }
  return payload;
}

export const listModels = () => api<VisionModel[]>("/vision/models");
export const listProjects = () => api<Project[]>("/projects");
export const listJobs = (status = "") =>
  api<DetectionJob[]>(`/detections/jobs${status ? `?status=${status}` : ""}`);
export const getJob = (id: string) => api<DetectionJob>(`/detections/jobs/${id}`);
export const cancelJob = (id: string) =>
  api<DetectionJob>(`/detections/jobs/${id}/cancel`, { method: "POST" });
export const retryJob = (id: string) =>
  api<DetectionJob>(`/detections/jobs/${id}/retry`, { method: "POST" });
export const mediaUrl = (id: string) => `/api/v1/detections/media/${id}`;

export async function uploadImages(
  projectId: string,
  modelId: string,
  parameters: DetectionParameters,
  files: File[],
) {
  const form = new FormData();
  form.set("project_id", projectId);
  form.set("model_id", modelId);
  form.set("parameters", JSON.stringify(parameters));
  files.forEach((file) => form.append("files", file));
  return formRequest<Array<{ filename: string; job_id: string | null; error: string | null }>>(
    "/detections/images",
    form,
  );
}

export async function uploadVideo(
  projectId: string,
  modelId: string,
  parameters: DetectionParameters,
  file: File,
) {
  const form = new FormData();
  form.set("project_id", projectId);
  form.set("model_id", modelId);
  form.set("parameters", JSON.stringify(parameters));
  form.set("file", file);
  return formRequest<DetectionJob>("/detections/videos", form);
}

export const startObs = (projectId: string, modelId: string, parameters: DetectionParameters) =>
  api<DetectionJob>("/detections/obs", {
    method: "POST",
    body: jsonBody({ project_id: projectId, model_id: modelId, parameters }),
  });
export const updateObs = (id: string, parameters: Partial<DetectionParameters>) =>
  api<DetectionJob>(`/detections/obs/${id}`, {
    method: "PATCH",
    body: jsonBody(parameters),
  });
export const stopObs = (id: string) =>
  api<DetectionJob>(`/detections/obs/${id}/stop`, { method: "POST" });
