import type { AuditEvent } from "../api/client";
import { useI18n } from "../i18n";

export function AuditDetails({ event }: { event: AuditEvent }) {
  const { t } = useI18n();
  return <details className="audit-details"><summary>{t("details")}</summary><div><section><h3>BEFORE</h3><pre>{JSON.stringify(event.before_state, null, 2) || "—"}</pre></section><section><h3>AFTER</h3><pre>{JSON.stringify(event.after_state, null, 2) || "—"}</pre></section>{event.detail && <p>{event.detail}</p>}</div></details>;
}
