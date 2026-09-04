import { api, jsonBody } from "./client";

export interface Category {
  id: string; code: string; name_zh: string; name_en: string; color: string; enabled: boolean;
}
export interface DatasetVersion {
  id: string; dataset_id: string; version_number: number; status: "draft" | "frozen" | "training" | "published" | "archived";
  source: string; train_ratio: number; val_ratio: number; test_ratio: number; sample_count: number; annotation_count: number; byte_size: number; revision: number;
}
export interface Dataset {
  id: string; project_id: string; owner_id: string; name: string; description: string | null; status: "active" | "archived"; versions: DatasetVersion[];
}
export interface Annotation {
  id?: string; category_id: string; cx: number; cy: number; width: number; height: number;
}
export interface Sample {
  id: string; version_id: string; original_name: string; mime_type: string; byte_size: number; sha256: string; width: number | null; height: number | null;
  split: "unassigned" | "train" | "val" | "test"; review_status: "unreviewed" | "approved" | "changes_requested"; duplicate_group: string | null; revision: number; annotations: Annotation[];
}
export interface Finding {
  id: string; sample_id: string | null; code: string; severity: "info" | "warning" | "error"; message: string; suggestion: string | null;
}
export interface LifecycleJob {
  id: string; kind: string; status: string; version_id: string | null; model_version_id: string | null; result_json: Record<string, string | number> | null; progress: number; progress_detail: string | null; error_code: string | null; queued_at: string;
}
export interface ManagedModel {
  id: string; code: string; version_number: number; scene: string; size_variant: string; status: string; dataset_version_id: string | null; weight_artifact_id: string; model_card: string; metrics_json: Record<string, number | string>; published_at: string | null;
}
export interface Deployment {
  id: string; project_id: string; scene: string; model_version_id: string; previous_model_version_id: string | null; rollout_percent: number;
}

export const listDatasets = () => api<Dataset[]>("/datasets");
export const listCategories = () => api<Category[]>("/dataset-categories");
export const listSamples = (versionId: string) => api<Sample[]>(`/dataset-versions/${versionId}/samples?limit=500`);
export const createDataset = (payload: { project_id: string; name: string; description?: string }) => api<Dataset>("/admin/datasets", { method: "POST", body: jsonBody(payload) });
export const createVersion = (datasetId: string) => api<DatasetVersion>(`/admin/datasets/${datasetId}/versions`, { method: "POST", body: jsonBody({ source: "upload", train_ratio: 80, val_ratio: 10, test_ratio: 10 }) });
export async function importDataset(versionId: string, file: File) {
  const body = new FormData(); body.append("archive", file);
  return api<{ imported_samples: number; imported_annotations: number }>(`/admin/dataset-versions/${versionId}/import`, { method: "POST", body });
}
export async function importMedia(versionId: string, files: FileList) {
  const body = new FormData(); Array.from(files).forEach((file) => body.append("files", file));
  return api<{ imported_samples: number }>(`/admin/dataset-versions/${versionId}/media`, { method: "POST", body });
}
export const saveAnnotations = (sample: Sample, annotations: Annotation[]) => api<Sample>(`/dataset-samples/${sample.id}/annotations`, { method: "PUT", body: jsonBody({ expected_revision: sample.revision, annotations }) });
export const restoreAnnotations = (sample: Sample, operation: "undo" | "redo") => api<Sample>(`/dataset-samples/${sample.id}/annotations/${operation}`, { method: "POST", body: jsonBody({ expected_revision: sample.revision }) });
export const reviewSample = (sample: Sample, status: "approved" | "changes_requested") => api<Sample>(`/dataset-samples/${sample.id}/review`, { method: "POST", body: jsonBody({ expected_revision: sample.revision, status }) });
export const checkQuality = (versionId: string) => api<Finding[]>(`/admin/dataset-versions/${versionId}/quality`, { method: "POST" });
export const freezeVersion = (versionId: string) => api<DatasetVersion>(`/admin/dataset-versions/${versionId}/freeze`, { method: "POST" });
export const listJobs = () => api<LifecycleJob[]>("/lifecycle-jobs");
export const createTrainingJob = (versionId: string) => api<LifecycleJob>("/admin/lifecycle-jobs", { method: "POST", body: jsonBody({ version_id: versionId, kind: "train", config: { code: "infrasentinel-custom", scene: "pipeline", size_variant: "n", epochs: 5 } }) });
export const createExtractionJob = (versionId: string) => api<LifecycleJob>("/admin/lifecycle-jobs", { method: "POST", body: jsonBody({ version_id: versionId, kind: "extract", config: { interval_seconds: 1, max_frames: 1000 } }) });
export const createExportJob = (versionId: string) => api<LifecycleJob>("/admin/lifecycle-jobs", { method: "POST", body: jsonBody({ version_id: versionId, kind: "export", config: {} }) });
export const createEvaluationJob = (model: ManagedModel) => api<LifecycleJob>("/admin/lifecycle-jobs", { method: "POST", body: jsonBody({ version_id: model.dataset_version_id, kind: "evaluate", config: { model_version_id: model.id } }) });
export const listModels = () => api<ManagedModel[]>("/managed-models");
export const publishModel = (id: string) => api<ManagedModel>(`/admin/managed-models/${id}/publish`, { method: "POST" });
export const deployModel = (id: string, projectId: string) => api<Deployment>(`/admin/managed-models/${id}/deploy`, { method: "POST", body: jsonBody({ project_id: projectId, rollout_percent: 100 }) });
export const listDeployments = () => api<Deployment[]>("/model-deployments");
export const rollbackDeployment = (id: string) => api<Deployment>(`/admin/model-deployments/${id}/rollback`, { method: "POST" });
