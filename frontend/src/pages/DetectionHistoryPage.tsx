import { useEffect, useState } from "react";
import { Link } from "react-router";

import { cancelJob, listJobs, retryJob, type DetectionJob, type JobStatus } from "../api/detections";
import { useI18n } from "../i18n";

export function DetectionHistoryPage() {
  const { t } = useI18n();
  const [jobs, setJobs] = useState<DetectionJob[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  async function load() {
    try { setJobs(await listJobs(status)); setError(""); } catch (caught) { setError(String(caught)); }
  }
  useEffect(() => { void load(); }, [status]);
  async function act(action: (id: string) => Promise<DetectionJob>, job: DetectionJob) {
    try { await action(job.id); await load(); } catch (caught) { setError(String(caught)); }
  }
  const statuses: JobStatus[] = ["queued", "running", "cancelling", "cancelled", "succeeded", "failed"];
  return <><header className="page-heading"><div><p className="eyebrow">VISION / ARCHIVE</p><h1>{t("history")}</h1></div><button className="quiet-button" type="button" onClick={() => void load()}>{t("refresh")}</button></header><div className="history-filter"><label>{t("status")}<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">{t("empty")}</option>{statuses.map((item) => <option key={item} value={item}>{t(item)}</option>)}</select></label></div>{error && <p className="form-error">{error}</p>}<section className="job-list">{jobs.map((job) => <article key={job.id}><div className="job-head"><span className={`status-badge ${job.status}`}>{t(job.status)}</span><code>{job.kind.toUpperCase()}</code><time>{new Date(job.created_at).toLocaleString()}</time></div><progress max="100" value={job.progress_percent}>{job.progress_percent}%</progress><div className="job-meta"><span>{t("scene")}: {job.scene}</span><span>{t("progress")}: {job.progress_percent}%</span><span>#{job.attempt}/{job.max_attempts}</span></div>{job.error_detail && <p className="inline-error">{job.error_detail}</p>}<div className="row-actions"><Link className="quiet-button" to={`/detections/${job.id}`}>{t("viewDetails")}</Link>{["queued", "running"].includes(job.status) && <button type="button" onClick={() => void act(cancelJob, job)}>{t("cancel")}</button>}{["failed", "cancelled"].includes(job.status) && job.attempt < job.max_attempts && <button type="button" onClick={() => void act(retryJob, job)}>{t("retry")}</button>}</div></article>)}</section></>;
}
