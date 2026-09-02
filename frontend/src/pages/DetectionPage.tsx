import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import {
  listModels,
  listProjects,
  startObs,
  stopObs,
  updateObs,
  uploadImages,
  uploadVideo,
  type DetectionJob,
  type DetectionKind,
  type VisionModel,
} from "../api/detections";
import { useI18n } from "../i18n";

export function DetectionPage() {
  const { locale, t } = useI18n();
  const [kind, setKind] = useState<DetectionKind>("image");
  const [projects, setProjects] = useState<Array<{ id: string; code: string; name: string }>>([]);
  const [models, setModels] = useState<VisionModel[]>([]);
  const [projectId, setProjectId] = useState("");
  const [modelId, setModelId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [confidence, setConfidence] = useState(0.35);
  const [iou, setIou] = useState(0.7);
  const [inputSize, setInputSize] = useState(640);
  const [device, setDevice] = useState<"auto" | "cuda:0" | "cpu">("auto");
  const [detectionFps, setDetectionFps] = useState(15);
  const [resolution, setResolution] = useState<"640p" | "720p">("720p");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [live, setLive] = useState<DetectionJob | null>(null);
  const [preview, setPreview] = useState("");
  const [stale, setStale] = useState(false);

  useEffect(() => {
    void Promise.all([listProjects(), listModels()])
      .then(([projectItems, modelItems]) => {
        setProjects(projectItems);
        setModels(modelItems);
        setProjectId((value) => value || projectItems[0]?.id || "");
        const first = modelItems.find((model) => model.availability === "available");
        setModelId((value) => value || first?.id || "");
        setInputSize(first?.input_size ?? 640);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : String(caught)));
  }, []);

  useEffect(() => {
    if (!live || !["queued", "running"].includes(live.status)) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    let active = true;
    let socket: WebSocket | null = null;
    let reconnectTimer = 0;
    const connect = () => {
      socket = new WebSocket(
        `${protocol}://${location.host}/api/v1/detections/obs/${live.id}/preview`,
      );
      socket.binaryType = "blob";
      socket.onmessage = (event) => {
        if (event.data instanceof Blob) {
          setPreview(URL.createObjectURL(event.data));
          setStale(false);
        } else {
          setStale(true);
        }
      };
      socket.onclose = () => {
        setStale(true);
        if (active) reconnectTimer = window.setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      active = false;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [live]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const availableModels = useMemo(
    () => models.filter((model) => model.availability === "available"),
    [models],
  );
  const parameters = {
    confidence,
    iou,
    input_size: inputSize,
    device,
    detection_fps: detectionFps,
    resolution,
  };

  async function submit() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (kind === "image") {
        const result = await uploadImages(projectId, modelId, parameters, files);
        const accepted = result.filter((item) => item.job_id).length;
        setMessage(`${t("uploadComplete")} (${accepted}/${result.length})`);
      } else if (kind === "video") {
        const job = await uploadVideo(projectId, modelId, parameters, files[0]);
        setMessage(t("uploadComplete"));
        setFiles([]);
        location.assign(`/detections/${job.id}`);
      } else {
        setLive(await startObs(projectId, modelId, parameters));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function stopLive() {
    if (!live) return;
    try {
      setLive(await stopObs(live.id));
      setPreview("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    }
  }

  async function applyLiveParameters() {
    try {
      if (live) setLive(await updateObs(live.id, parameters));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    }
  }

  const needsFile = kind !== "obs";
  const disabled = busy || !projectId || !modelId || (needsFile && files.length === 0);

  return (
    <>
      <header className="page-heading">
        <div><p className="eyebrow">VISION / INFERENCE</p><h1>{t("detection")}</h1></div>
        <Link className="quiet-button" to="/detections/history">{t("history")}</Link>
      </header>
      <section className="detection-console">
        <div className="mode-tabs" role="tablist">
          {(["image", "video", "obs"] as DetectionKind[]).map((item) => (
            <button key={item} className={kind === item ? "active" : ""} type="button" onClick={() => { setKind(item); setFiles([]); }}>
              {t(item === "image" ? "imageDetection" : item === "video" ? "videoDetection" : "obsDetection")}
            </button>
          ))}
        </div>
        <div className="detection-form">
          <label>{t("selectProject")}<select value={projectId} onChange={(event) => setProjectId(event.target.value)}>{projects.map((project) => <option key={project.id} value={project.id}>{project.code} · {project.name}</option>)}</select></label>
          <label>{t("selectModel")}<select value={modelId} onChange={(event) => { const value = event.target.value; setModelId(value); setInputSize(availableModels.find((model) => model.id === value)?.input_size ?? 640); }}>{availableModels.map((model) => <option key={model.id} value={model.id}>{locale === "zh-CN" ? model.name_zh : model.name_en} · {model.version_label}</option>)}</select></label>
          <label>{t("confidence")}<input type="number" min="0.01" max="1" step="0.01" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} /></label>
          <label>{t("iou")}<input type="number" min="0.01" max="1" step="0.01" value={iou} onChange={(event) => setIou(Number(event.target.value))} /></label>
          <label>{t("inputSize")}<select value={inputSize} onChange={(event) => setInputSize(Number(event.target.value))}>{[320, 640, 960, 1280].map((size) => <option key={size} value={size}>{size} px</option>)}</select></label>
          <label>{t("devicePolicy")}<select value={device} onChange={(event) => setDevice(event.target.value as "auto" | "cuda:0" | "cpu")}><option value="auto">AUTO</option><option value="cuda:0">CUDA:0</option><option value="cpu">CPU</option></select></label>
          {kind !== "image" && <label>{t("detectionFps")}<input type="number" min={kind === "obs" ? 1 : 0.5} max="30" step="0.5" value={detectionFps} onChange={(event) => setDetectionFps(Number(event.target.value))} /></label>}
          {kind === "obs" && <label>{t("resolution")}<select value={resolution} onChange={(event) => setResolution(event.target.value as "640p" | "720p")}><option value="640p">640p</option><option value="720p">720p</option></select></label>}
          {needsFile && <label className="file-control">{t("chooseFiles")}<input type="file" accept={kind === "image" ? "image/jpeg,image/png,image/webp" : "video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"} multiple={kind === "image"} onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /><small>{files.map((file) => file.name).join(", ")}</small></label>}
        </div>
        {!availableModels.length && <p className="form-error">{t("noAvailableModel")}</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {message && <p className="success-note" role="status">{message}</p>}
        <div className="console-actions">
          <button className="primary-button" type="button" disabled={disabled} onClick={() => void submit()}>{kind === "obs" ? t("startLive") : t("submitDetection")}</button>
          {live && ["queued", "running"].includes(live.status) && <><button className="quiet-button" type="button" onClick={() => void applyLiveParameters()}>{t("save")}</button><button className="danger-button" type="button" onClick={() => void stopLive()}>{t("stopLive")}</button></>}
        </div>
      </section>
      {live && <section className="live-panel"><div className="section-label"><span>LIVE</span>{t("livePreview")}</div><div className="preview-frame">{preview ? <img src={preview} alt={t("livePreview")} /> : <p>{stale ? t("previewStale") : t("previewWaiting")}</p>}</div><dl><div><dt>{t("status")}</dt><dd className={`status-badge ${live.status}`}>{t(live.status)}</dd></div><div><dt>{t("model")}</dt><dd>{live.model_id}</dd></div></dl></section>}
    </>
  );
}
