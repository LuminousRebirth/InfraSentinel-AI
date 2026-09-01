import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, type AuditEvent } from "../api/client";
import { AuditDetails } from "../components/AuditDetails";
import { useI18n } from "../i18n";

export function AdminAuditPage() {
  const { locale, t } = useI18n();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async (before?: string) => {
    const query = new URLSearchParams({ limit: "50" });
    if (action) query.set("action", action);
    if (before) query.set("before", before);
    try { const rows = await api<AuditEvent[]>(`/admin/audit-events?${query}`); setEvents((current) => before ? [...current, ...rows] : rows); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Request failed"); }
  }, [action]);
  useEffect(() => { void load(); }, [load]);
  function filter(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); setAction(String(data.get("action") ?? "")); }
  return <><header className="page-heading"><div><p className="eyebrow">GOVERNANCE / IMMUTABLE LOG</p><h1>{t("audit")}</h1></div></header><form className="audit-filter" onSubmit={filter}><label>{t("filterAction")}<input name="action" defaultValue={action} placeholder="admin.user_status" /></label><button>{t("save")}</button></form>{error && <p className="form-error" role="alert">{error}</p>}<div className="audit-list">{events.length ? events.map((item) => <article key={item.id}><div className="audit-line"><time>{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}</time><code>{item.action}</code><span className={`result ${item.result}`}>{t(item.result)}</span><span>{item.target_type} / {item.target_id?.slice(0, 8) ?? "system"}</span></div><AuditDetails event={item} /></article>) : <p className="empty-state">{t("empty")}</p>}</div>{events.length >= 50 && <button className="load-more" onClick={() => void load(events.at(-1)?.created_at)}>{t("loadMore")}</button>}</>;
}
