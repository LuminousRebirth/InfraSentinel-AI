import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import { api, type Project } from "../api/client";
import {
  checkQuality, createDataset, createEvaluationJob, createExportJob, createExtractionJob, createTrainingJob, createVersion, deployModel, freezeVersion, importDataset, importMedia,
  listCategories, listDatasets, listDeployments, listJobs, listModels, listSamples,
  publishModel, restoreAnnotations, reviewSample, rollbackDeployment, saveAnnotations, type Annotation, type Category,
  type Dataset, type Deployment, type Finding, type LifecycleJob, type ManagedModel, type Sample,
} from "../api/lifecycle";
import { useI18n } from "../i18n";

const zhCN = {
  title: "数据与模型工坊", subtitle: "从现场样本到上线模型，每次变更都留有版本和审计轨迹。", datasets: "数据集", modelVersions: "模型版本",
  stages: ["导入", "标注", "质检", "训练", "部署"], progress: "生命周期进度", loadFailed: "加载失败", actionFailed: "操作失败",
  project: "项目", datasetName: "数据集名称", datasetExample: "例如：东区管廊九月巡检", description: "说明", descriptionHint: "采集区域、设备与时间范围",
  createDataset: "新建数据集", currentDataset: "当前数据集", importZip: "导入 YOLO ZIP", addMedia: "添加图片或视频", datasetCreated: "数据集已创建",
  imported: "数据已导入并完成稳定拆分", mediaImported: "媒体已导入", samples: "样本", annotations: "标注", split: "拆分", revision: "修订",
  extractFrames: "视频抽帧", runQuality: "运行质量检查", freeze: "冻结版本", exportYolo: "导出 YOLO", train: "开始训练", newVersion: "新建版本",
  extractionQueued: "抽帧任务已进入队列", qualityPassed: "质量检查通过", qualityFailed: "质检失败", qualityIssues: (count: number) => `发现 ${count} 个质量问题`,
  frozen: "版本已冻结", exportQueued: "导出任务已进入队列", trainingQueued: "训练任务已进入队列", versionCreated: "新草稿版本已创建",
  sampleCatalog: "样本目录", boxes: "个框", samplesEmpty: "导入 ZIP 后，样本会在这里逐条展开。", datasetEmpty: "先创建一个数据集，系统会自动建立首个草稿版本。",
  annotationSaved: "标注已保存", undone: "已撤销上次标注", redone: "已重做标注", reviewApproved: "样本已通过复核", changesRequested: "已要求修改",
  releaseRack: "模型发布架", processing: (count: number) => `${count} 个任务处理中`, evaluate: "评估", publish: "发布", deploy: "部署到首个项目", rollback: "回滚",
  evaluationQueued: "评估任务已进入队列", published: "模型已发布", deployed: "模型已部署", rolledBack: "部署已回滚", precision: "精确率", downloadArtifact: "下载产物", downloadWeights: "下载权重",
  chooseSample: "选择一个样本开始标注。", canvas: "标注画布", addBox: "添加框", undo: "撤销", redo: "重做", approveReview: "通过复核", requestChanges: "要求修改", saveAnnotations: "保存标注",
} as const;

const en = {
  title: "Data & model workshop", subtitle: "Every change from field sample to deployed model retains a versioned audit trail.", datasets: "Datasets", modelVersions: "Model versions",
  stages: ["Import", "Annotate", "Inspect", "Train", "Deploy"], progress: "Lifecycle progress", loadFailed: "Loading failed", actionFailed: "Action failed",
  project: "Project", datasetName: "Dataset name", datasetExample: "Example: East conduit September inspection", description: "Description", descriptionHint: "Collection area, equipment, and time range",
  createDataset: "Create dataset", currentDataset: "Current dataset", importZip: "Import YOLO ZIP", addMedia: "Add images or video", datasetCreated: "Dataset created",
  imported: "Data imported and deterministically split", mediaImported: "Media imported", samples: "Samples", annotations: "Annotations", split: "Split", revision: "Revision",
  extractFrames: "Extract video frames", runQuality: "Run quality checks", freeze: "Freeze version", exportYolo: "Export YOLO", train: "Start training", newVersion: "New version",
  extractionQueued: "Frame extraction queued", qualityPassed: "Quality checks passed", qualityFailed: "Quality check failed", qualityIssues: (count) => `${count} quality issue${count === 1 ? "" : "s"} found`,
  frozen: "Version frozen", exportQueued: "Export queued", trainingQueued: "Training queued", versionCreated: "New draft version created",
  sampleCatalog: "Sample catalog", boxes: "boxes", samplesEmpty: "Samples appear here after importing a YOLO ZIP.", datasetEmpty: "Create a dataset to begin with its first draft version.",
  annotationSaved: "Annotations saved", undone: "Last annotation change undone", redone: "Annotation change restored", reviewApproved: "Sample approved", changesRequested: "Changes requested",
  releaseRack: "Model release rack", processing: (count) => `${count} job${count === 1 ? "" : "s"} processing`, evaluate: "Evaluate", publish: "Publish", deploy: "Deploy to first project", rollback: "Rollback",
  evaluationQueued: "Evaluation queued", published: "Model published", deployed: "Model deployed", rolledBack: "Deployment rolled back", precision: "Precision", downloadArtifact: "Download artifact", downloadWeights: "Download weights",
  chooseSample: "Select a sample to start annotating.", canvas: "Annotation canvas", addBox: "Add box", undo: "Undo", redo: "Redo", approveReview: "Approve", requestChanges: "Request changes", saveAnnotations: "Save annotations",
} satisfies Record<keyof typeof zhCN, string | readonly string[] | ((count: number) => string)>;

export function AdminLifecyclePage() {
  const { locale } = useI18n();
  const c = locale === "en" ? en : zhCN;
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [jobs, setJobs] = useState<LifecycleJob[]>([]);
  const [models, setModels] = useState<ManagedModel[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [selectedSampleId, setSelectedSampleId] = useState("");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [datasetRows, projectRows, categoryRows, jobRows, modelRows, deploymentRows] = await Promise.all([
        listDatasets(), api<Project[]>("/projects"), listCategories(), listJobs(), listModels(), listDeployments(),
      ]);
      setDatasets(datasetRows); setProjects(projectRows); setCategories(categoryRows);
      setJobs(jobRows); setModels(modelRows); setDeployments(deploymentRows);
      setSelectedDatasetId((value) => value || datasetRows[0]?.id || "");
    } catch (error) { setMessage(error instanceof Error ? error.message : c.loadFailed as string); }
  }, [c.loadFailed]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  const dataset = datasets.find((item) => item.id === selectedDatasetId);
  const version = dataset?.versions[0];
  useEffect(() => {
    if (!version) { setSamples([]); return; }
    void listSamples(version.id).then((rows) => {
      setSamples(rows); setSelectedSampleId((value) => rows.some((x) => x.id === value) ? value : rows[0]?.id || "");
    }).catch((error: Error) => setMessage(error.message));
  }, [version?.id]);
  const sample = samples.find((item) => item.id === selectedSampleId);
  const stage = !version?.sample_count ? 0 : version.status === "draft" ? (findings.length ? 2 : 1) : models.length ? (deployments.length ? 4 : 3) : 3;

  async function perform(action: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage("");
    try { await action(); setMessage(success); await load(); }
    catch (error) { setMessage(error instanceof Error ? error.message : c.actionFailed as string); }
    finally { setBusy(false); }
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement);
    await perform(async () => {
      const created = await createDataset({ project_id: String(form.get("project")), name: String(form.get("name")), description: String(form.get("description")) });
      setSelectedDatasetId(created.id); formElement.reset();
    }, c.datasetCreated as string);
  }

  async function onImport(file?: File) {
    if (!file || !version) return;
    await perform(() => importDataset(version.id, file), c.imported as string);
  }

  async function onQuality() {
    if (!version) return;
    setBusy(true);
    try { const rows = await checkQuality(version.id); setFindings(rows); setMessage(rows.length ? c.qualityIssues(rows.length) : c.qualityPassed as string); }
    catch (error) { setMessage(error instanceof Error ? error.message : c.qualityFailed as string); }
    finally { setBusy(false); }
  }

  return <section className="lifecycle-page">
    <header className="lifecycle-heading">
      <div><p className="eyebrow">DATA PROVENANCE / MODEL CONTROL</p><h1>{c.title}</h1><p>{c.subtitle}</p></div>
      <div className="lifecycle-tally"><strong>{String(datasets.length).padStart(2, "0")}</strong><span>{c.datasets}</span><strong>{String(models.length).padStart(2, "0")}</strong><span>{c.modelVersions}</span></div>
    </header>
    <div className="provenance-rail" aria-label={c.progress as string}>{c.stages.map((label, index) => <div className={index <= stage ? "reached" : ""} key={label}><i /><span>{label}</span></div>)}</div>
    {message && <p className="notice-strip" role="status">{message}</p>}

    <section className="lifecycle-controls">
      <form onSubmit={(event) => void onCreate(event)}>
        <label>{c.project}<select name="project" required>{projects.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label>{c.datasetName}<input name="name" required placeholder={c.datasetExample as string} /></label>
        <label>{c.description}<input name="description" placeholder={c.descriptionHint as string} /></label>
        <button disabled={busy || !projects.length} className="primary-button">{c.createDataset}</button>
      </form>
      <label>{c.currentDataset}<select value={selectedDatasetId} onChange={(event) => { setSelectedDatasetId(event.target.value); setFindings([]); }}>{datasets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="archive-drop">{c.importZip}<input type="file" accept=".zip,application/zip" disabled={busy || version?.status !== "draft"} onChange={(event) => void onImport(event.target.files?.[0])} /></label>
      <label className="archive-drop">{c.addMedia}<input type="file" multiple accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska" disabled={busy || version?.status !== "draft"} onChange={(event) => { if (event.target.files && version) void perform(() => importMedia(version.id, event.target.files!), c.mediaImported as string); }} /></label>
    </section>

    {version ? <>
      <div className="version-ledger">
        <span>V{version.version_number}</span><span className={`version-state ${version.status}`}>{version.status}</span>
        <dl><div><dt>{c.samples}</dt><dd>{version.sample_count}</dd></div><div><dt>{c.annotations}</dt><dd>{version.annotation_count}</dd></div><div><dt>{c.split}</dt><dd>80 / 10 / 10</dd></div><div><dt>{c.revision}</dt><dd>R{version.revision}</dd></div></dl>
        <div><button type="button" disabled={busy || version.status !== "draft"} onClick={() => void perform(() => createExtractionJob(version.id), c.extractionQueued as string)}>{c.extractFrames}</button><button type="button" disabled={busy || version.status !== "draft"} onClick={() => void onQuality()}>{c.runQuality}</button><button type="button" disabled={busy || version.status !== "draft"} onClick={() => void perform(() => freezeVersion(version.id), c.frozen as string)}>{c.freeze}</button><button type="button" disabled={busy || version.status !== "frozen"} onClick={() => void perform(() => createExportJob(version.id), c.exportQueued as string)}>{c.exportYolo}</button><button type="button" disabled={busy || version.status !== "frozen"} onClick={() => void perform(() => createTrainingJob(version.id), c.trainingQueued as string)}>{c.train}</button><button type="button" disabled={busy || !dataset} onClick={() => dataset && void perform(() => createVersion(dataset.id), c.versionCreated as string)}>{c.newVersion}</button></div>
      </div>
      {findings.length > 0 && <div className="quality-strip">{findings.map((item) => <span className={item.severity} key={item.id}>{item.code} · {item.message}</span>)}</div>}
      <div className="annotation-bench">
        <aside><h2>{c.sampleCatalog}</h2>{samples.length ? samples.map((item) => <button className={item.id === selectedSampleId ? "active" : ""} type="button" key={item.id} onClick={() => setSelectedSampleId(item.id)}><span>{item.original_name}</span><small>{item.split} · {item.annotations.length} {c.boxes}</small></button>) : <p>{c.samplesEmpty}</p>}</aside>
        <AnnotationDesk sample={sample} categories={categories} locale={locale} copy={c} busy={busy} onSave={(annotations) => sample && perform(async () => { const updated = await saveAnnotations(sample, annotations); setSamples((rows) => rows.map((item) => item.id === updated.id ? updated : item)); }, c.annotationSaved as string)} onRestore={(operation) => sample && perform(async () => { const updated = await restoreAnnotations(sample, operation); setSamples((rows) => rows.map((item) => item.id === updated.id ? updated : item)); }, operation === "undo" ? c.undone as string : c.redone as string)} onReview={(status) => sample && perform(async () => { const updated = await reviewSample(sample, status); setSamples((rows) => rows.map((item) => item.id === updated.id ? updated : item)); }, status === "approved" ? c.reviewApproved as string : c.changesRequested as string)} />
      </div>
    </> : <div className="lifecycle-empty">{c.datasetEmpty}</div>}

    <section className="model-rack"><header><div><p className="eyebrow">RELEASE RACK</p><h2>{c.releaseRack}</h2></div><span>{c.processing(jobs.filter((item) => item.status === "running" || item.status === "queued").length)}</span></header>
      <div className="job-tape">{jobs.slice(0, 8).map((job) => <div key={job.id}><code>{job.kind.toUpperCase()}</code><span>{job.status}</span><progress value={job.progress} max="100" />{typeof job.result_json?.artifact_id === "string" && <a href={`/api/v1/lifecycle-artifacts/${job.result_json.artifact_id}`}>{c.downloadArtifact}</a>}</div>)}</div>
      <div className="model-grid">{models.map((model) => { const deployed = deployments.find((item) => item.model_version_id === model.id); const evaluated = jobs.some((job) => job.kind === "evaluate" && job.model_version_id === model.id && job.status === "succeeded"); return <article key={model.id}><span className="model-code">{model.code} / V{model.version_number}</span><h3>{model.scene} · YOLO {model.size_variant.toUpperCase()}</h3><p>mAP50 {String(model.metrics_json.map50 ?? "—")} · {c.precision} {String(model.metrics_json.precision ?? "—")}</p><p className="model-card">{model.model_card}</p><div><span className={`version-state ${model.status}`}>{model.status}</span><a href={`/api/v1/lifecycle-artifacts/${model.weight_artifact_id}`}>{c.downloadWeights}</a>{model.status !== "published" && !evaluated && <button type="button" disabled={!model.dataset_version_id} onClick={() => void perform(() => createEvaluationJob(model), c.evaluationQueued as string)}>{c.evaluate}</button>}{model.status !== "published" && evaluated && <button type="button" onClick={() => void perform(() => publishModel(model.id), c.published as string)}>{c.publish}</button>}{model.status === "published" && !deployed && <button type="button" disabled={!projects[0]} onClick={() => void perform(() => deployModel(model.id, projects[0].id), c.deployed as string)}>{c.deploy}</button>}{deployed?.previous_model_version_id && <button type="button" onClick={() => void perform(() => rollbackDeployment(deployed.id), c.rolledBack as string)}>{c.rollback}</button>}</div></article>; })}</div>
    </section>
  </section>;
}

function AnnotationDesk({ sample, categories, locale, copy, busy, onSave, onRestore, onReview }: { sample?: Sample; categories: Category[]; locale: string; copy: typeof zhCN | typeof en; busy: boolean; onSave: (items: Annotation[]) => void; onRestore: (operation: "undo" | "redo") => void; onReview: (status: "approved" | "changes_requested") => void }) {
  const [items, setItems] = useState<Annotation[]>([]);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number }>();
  const [selected, setSelected] = useState<number>();
  useEffect(() => setItems(sample?.annotations ?? []), [sample?.id, sample?.revision]);
  const categoryMap = useMemo(() => new Map(categories.map((item) => [item.id, item])), [categories]);
  function point(event: ReactPointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: (event.clientX - bounds.left) / bounds.width, y: (event.clientY - bounds.top) / bounds.height };
  }
  function finishDraw(event: ReactPointerEvent<SVGSVGElement>) {
    if (!drawStart || !categories[0]) return;
    const end = point(event); const width = Math.abs(end.x - drawStart.x); const height = Math.abs(end.y - drawStart.y);
    if (width >= .01 && height >= .01) setItems((rows) => [...rows, { category_id: categories[0].id, cx: (end.x + drawStart.x) / 2, cy: (end.y + drawStart.y) / 2, width, height }]);
    setDrawStart(undefined);
  }
  if (!sample) return <div className="annotation-desk empty"><p>{copy.chooseSample}</p></div>;
  return <div className="annotation-desk" tabIndex={0} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); onRestore(event.shiftKey ? "redo" : "undo"); } }}><div className="sample-stage"><div className="image-plane"><img src={`/api/v1/dataset-samples/${sample.id}/content`} alt={sample.original_name} /><svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-label={copy.canvas as string} onPointerDown={(event) => setDrawStart(point(event))} onPointerUp={finishDraw}>{items.map((box, index) => <g key={index} onPointerDown={(event) => { event.stopPropagation(); setSelected(index); }}><rect className={selected === index ? "selected" : ""} x={box.cx - box.width / 2} y={box.cy - box.height / 2} width={box.width} height={box.height} style={{ stroke: categoryMap.get(box.category_id)?.color }} /><text x={box.cx - box.width / 2} y={Math.max(.025, box.cy - box.height / 2)}>{categoryMap.get(box.category_id)?.code}</text></g>)}</svg></div></div><div className="box-editor"><header><div><h2>{sample.original_name}</h2><small>{sample.width} × {sample.height} · {copy.revision} {sample.revision} · {sample.review_status}</small></div><button type="button" onClick={() => setItems((rows) => [...rows, { category_id: categories[0]?.id ?? "", cx: .5, cy: .5, width: .25, height: .25 }])}>{copy.addBox}</button></header><div className="annotation-toolbar"><button type="button" disabled={busy} onClick={() => onRestore("undo")}>{copy.undo}</button><button type="button" disabled={busy} onClick={() => onRestore("redo")}>{copy.redo}</button><button type="button" disabled={busy} onClick={() => onReview("approved")}>{copy.approveReview}</button><button type="button" disabled={busy} onClick={() => onReview("changes_requested")}>{copy.requestChanges}</button></div>{items.map((box, index) => <div className={`box-row ${selected === index ? "selected" : ""}`} key={index} onClick={() => setSelected(index)}><select value={box.category_id} onChange={(event) => setItems((rows) => rows.map((item, i) => i === index ? { ...item, category_id: event.target.value } : item))}>{categories.filter((item) => item.enabled).map((item) => <option value={item.id} key={item.id}>{item.code} · {locale === "en" ? item.name_en : item.name_zh}</option>)}</select>{(["cx", "cy", "width", "height"] as const).map((key) => <label key={key}>{key}<input type="number" min="0" max="1" step="0.01" value={box[key]} onChange={(event) => setItems((rows) => rows.map((item, i) => i === index ? { ...item, [key]: Number(event.target.value) } : item))} /></label>)}<button type="button" className="remove-box" onClick={() => setItems((rows) => rows.filter((_, i) => i !== index))}>×</button></div>)}<button className="primary-button save-boxes" type="button" disabled={busy} onClick={() => onSave(items)}>{copy.saveAnnotations}</button></div></div>;
}
