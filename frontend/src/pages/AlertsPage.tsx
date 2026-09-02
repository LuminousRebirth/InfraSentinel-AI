import { useEffect, useMemo, useState } from "react";

import {
  analyzeAlert,
  deletePersonalCredential,
  getAlert,
  getAlerts,
  getProviders,
  saveCredential,
  updateAlert,
  uploadAlertAttachment,
  type Alert,
  type AlertDetail,
  type Analysis,
  type Provider,
} from "../api/intelligence";
import { ApiError } from "../api/client";
import { useSession } from "../auth/session";
import { useI18n } from "../i18n";

const statusLabel: Record<Alert["status"], string> = {
  pending_confirmation: "待确认",
  assigned: "已分派",
  processing: "处理中",
  resolved: "已解决",
  false_positive: "误报",
};

export function AlertsPage() {
  const { locale, t } = useI18n();
  const { user } = useSession();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerId, setProviderId] = useState("");
  const [personalKey, setPersonalKey] = useState("");
  const [note, setNote] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const selected = useMemo(
    () => alerts.find((item) => item.id === selectedId) ?? alerts[0] ?? null,
    [alerts, selectedId],
  );
  const filtered = useMemo(
    () => alerts.filter((item) => (!statusFilter || item.status === statusFilter) && (!levelFilter || item.final_level === levelFilter)),
    [alerts, statusFilter, levelFilter],
  );

  async function load() {
    setLoading(true);
    try {
      const items = await getAlerts();
      setAlerts(items);
      const providerItems = await getProviders();
      setProviders(providerItems);
      setProviderId((current) => current || providerItems[0]?.id || "");
      setError("");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "告警加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    void getAlert(selected.id).then((value) => { setDetail(value); setAnalysis(value.analysis); }).catch(() => setDetail(null));
  }, [selected?.id]);

  async function applyWorkflow(status: Alert["status"], assigneeId?: string) {
    if (!selected) return;
    try {
      const updated = await updateAlert(selected.id, {
        expected_version: selected.version,
        status,
        assignee_id: assigneeId,
        note: note || undefined,
      });
      setAlerts((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNote("");
      setDetail(await getAlert(updated.id));
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "处置失败"); }
  }

  async function attach(file: File) {
    if (!selected) return;
    try {
      await uploadAlertAttachment(selected.id, file);
      setDetail(await getAlert(selected.id));
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "附件上传失败"); }
  }

  async function storePersonalKey() {
    if (!providerId || personalKey.length < 8) return;
    try {
      await saveCredential(providerId, personalKey, false);
      setPersonalKey("");
      setError("");
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "密钥保存失败"); }
  }

  async function requestAnalysis(preferPersonal: boolean) {
    if (!selected) return;
    try {
      setAnalysis(await analyzeAlert(selected.id, preferPersonal));
      setError("");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "分析请求失败");
    }
  }

  return (
    <section className="alert-center">
      <header className="alert-heading">
        <div><span className="section-kicker">EVENT DESK</span><h1>{t("alerts")}</h1></div>
        <button className="quiet-button" type="button" onClick={() => void load()}>{t("refresh")}</button>
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="alert-console">
        <div className="alert-rail" aria-label="Alert list">
          <div className="alert-filters"><select aria-label={t("status")} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">{t("status")}: {t("all")}</option>{Object.entries(statusLabel).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><select aria-label={t("riskLevel")} value={levelFilter} onChange={(event) => setLevelFilter(event.target.value)}><option value="">{t("riskLevel")}: {t("all")}</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select></div>
          {loading && <p className="empty-state">{t("loading")}</p>}
          {!loading && alerts.length === 0 && <p className="empty-state">{t("noAlerts")}</p>}
          {filtered.map((item) => (
            <button
              className={`alert-row ${selected?.id === item.id ? "active" : ""}`}
              key={item.id}
              type="button"
              onClick={() => { setSelectedId(item.id); setAnalysis(null); }}
            >
              <span className={`risk-signal ${item.final_level}`} aria-hidden="true" />
              <span><strong>{locale === "en" ? item.title_en : item.title_zh}</strong><small>{item.summary}</small></span>
              <time>{new Date(item.created_at).toLocaleString(locale)}</time>
            </button>
          ))}
        </div>
        <article className="alert-sheet">
          {!selected ? <p className="empty-state">{t("selectAlert")}</p> : <>
            <div className="alert-sheet-title">
              <div><span className={`level-stamp ${selected.final_level}`}>{selected.final_level}</span><h2>{locale === "en" ? selected.title_en : selected.title_zh}</h2></div>
              <span className="status-tag">{statusLabel[selected.status]}</span>
            </div>
            <dl className="alert-facts">
              <div><dt>事件编号</dt><dd>{selected.event_id}</dd></div>
              <div><dt>检测摘要</dt><dd>{selected.summary || "—"}</dd></div>
              <div><dt>当前负责人</dt><dd>{selected.assignee_id || "尚未分派"}</dd></div>
              <div><dt>更新时间</dt><dd>{new Date(selected.updated_at).toLocaleString(locale)}</dd></div>
            </dl>
            <section className="workflow-panel">
              <h3>{t("alertHandling")}</h3>
              {selected.status === "pending_confirmation" && user?.role === "admin" && <button type="button" onClick={() => void applyWorkflow("assigned", selected.owner_id)}>{t("assignOwner")}</button>}
              {selected.status === "assigned" && <button type="button" onClick={() => void applyWorkflow("processing")}>{t("startHandling")}</button>}
              {selected.status === "processing" && <>
                <label>{t("handlingNote")}<textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} /></label>
                <div className="button-row"><button disabled={!note.trim()} type="button" onClick={() => void applyWorkflow("resolved")}>{t("resolveAlert")}</button><button disabled={!note.trim()} className="quiet-button" type="button" onClick={() => void applyWorkflow("false_positive")}>{t("markFalsePositive")}</button></div>
              </>}
              <label className="attachment-control">{t("addEvidence")}<input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(event) => { const file = event.target.files?.[0]; if (file) void attach(file); }} /></label>
              {detail && <div className="timeline">{detail.actions.map((item) => <div key={item.id}><strong>{item.action}</strong><span>{item.detail || new Date(item.created_at).toLocaleString(locale)}</span></div>)}</div>}
              {detail?.attachments.map((item) => <a key={item.id} href={`/api/v1/alerts/attachments/${item.id}`}>{item.original_name}</a>)}
            </section>
            <section className="analysis-panel">
              <div><span className="section-kicker">VISION REASONING</span><h3>{t("modelAnalysis")}</h3></div>
              {analysis ? <div className="analysis-result">
                <strong>{analysis.status}</strong>
                <p>{analysis.error_code || (analysis.result_json ? JSON.stringify(analysis.result_json, null, 2) : t("analysisQueued"))}</p>
              </div> : <p>{t("analysisAdvisory")}</p>}
              <div className="button-row">
                <button type="button" onClick={() => void requestAnalysis(false)}>{t("useSystemModel")}</button>
                <button className="quiet-button" type="button" onClick={() => void requestAnalysis(true)}>{t("usePersonalModel")}</button>
              </div>
              <details className="personal-key"><summary>{t("personalCredential")}</summary>
                <label>{t("modelProviders")}<select value={providerId} onChange={(event) => setProviderId(event.target.value)}>{providers.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
                <label>API Key<input type="password" autoComplete="new-password" value={personalKey} onChange={(event) => setPersonalKey(event.target.value)} /></label>
                <button type="button" disabled={!providerId || personalKey.length < 8} onClick={() => void storePersonalKey()}>{t("savePersonalCredential")}</button>
                <button className="quiet-button" type="button" disabled={!providerId} onClick={() => void deletePersonalCredential(providerId)}>{t("deletePersonalCredential")}</button>
              </details>
            </section>
          </>}
        </article>
      </div>
    </section>
  );
}
