import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { getJob, mediaUrl, type DetectionJob } from "../api/detections";
import { useI18n } from "../i18n";

export function DetectionDetailPage() {
  const { id = "" } = useParams();
  const { t } = useI18n();
  const [job, setJob] = useState<DetectionJob | null>(null);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let timer = 0;
    const load = async () => {
      try {
        const current = await getJob(id);
        if (!active) return;
        setJob(current);
        setError("");
        if (["queued", "running", "cancelling"].includes(current.status)) timer = window.setTimeout(load, 1500);
      } catch (caught) { if (active) setError(String(caught)); }
    };
    void load();
    return () => { active = false; window.clearTimeout(timer); };
  }, [id]);
  const original = job?.media.find((item) => item.role === "original");
  const annotated = job?.media.find((item) => item.role === "annotated");
  const observation = job?.observations[selected];
  return <><header className="page-heading"><div><p className="eyebrow">VISION / EVIDENCE</p><h1>{t("details")}</h1></div><Link className="quiet-button" to="/detections/history">{t("history")}</Link></header>{error && <p className="form-error">{error}</p>}{!job ? <p>{t("loading")}</p> : <><section className="detail-summary"><span className={`status-badge ${job.status}`}>{t(job.status)}</span><progress max="100" value={job.progress_percent}>{job.progress_percent}%</progress><code>{job.id}</code><span>{t("model")}: {job.model_id}</span></section><section className="media-grid">{[original, annotated].map((media, index) => media && <article key={media.id}><h2>{t(index ? "annotatedMedia" : "originalMedia")}</h2>{media.media_type === "image" ? <img src={mediaUrl(media.id)} alt={media.original_name} /> : <video controls src={mediaUrl(media.id)} />}{media.media_type === "video" && index === 1 && <p className="media-note">{t("audioNotRetained")}</p>}</article>)}</section><section className="objects-panel"><h2>{t("objects")} ({job.observations.length})</h2><div className="object-layout"><div className="object-list">{job.observations.map((item, index) => <button className={selected === index ? "active" : ""} type="button" key={item.id} onClick={() => setSelected(index)}><strong>{item.class_name}</strong><span>{(item.confidence * 100).toFixed(1)}%</span><time>{(item.timestamp_ms / 1000).toFixed(2)}s</time></button>)}</div>{observation && <dl><div><dt>{t("className")}</dt><dd>{observation.class_name}</dd></div><div><dt>{t("confidence")}</dt><dd>{observation.confidence.toFixed(3)}</dd></div><div><dt>{t("coordinates")}</dt><dd>{[observation.x1, observation.y1, observation.x2, observation.y2].join(", ")}</dd></div><div><dt>{t("inferenceTime")}</dt><dd>{observation.inference_ms} ms</dd></div></dl>}</div></section></>}</>;
}
