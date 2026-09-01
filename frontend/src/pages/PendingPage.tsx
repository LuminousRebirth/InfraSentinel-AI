import type { ReactNode } from "react";
import { Link } from "react-router";

import { useSession } from "../auth/session";
import { useI18n } from "../i18n";

export function PendingPage({ switcher }: { switcher: ReactNode }) {
  const { user, logout } = useSession();
  const { t } = useI18n();
  const status = user?.status ?? "pending";
  const title = status === "disabled" ? t("disabledTitle") : status === "rejected" ? t("rejectedTitle") : t("pendingTitle");
  return (
    <main className="holding-page">
      <div className="holding-top"><span className="auth-brand"><span className="brand-mark">IS</span><strong>{t("brand")}</strong></span>{switcher}</div>
      <section className="holding-card">
        <p className="eyebrow">ACCESS REVIEW / 03</p><span className={`large-status ${status}`}>{t(status)}</span>
        <h1>{title}</h1><p>{status === "rejected" && user?.rejection_reason ? user.rejection_reason : t("pendingBody")}</p>
        <div className="route-diagram" aria-hidden="true"><span className="route-node active">01</span><i /><span className="route-node active">02</span><i /><span className="route-node active">03</span></div>
        {user ? <button className="quiet-button" onClick={() => void logout()}>{t("logout")}</button> : <Link className="primary-link" to="/login">{t("login")}</Link>}
      </section>
    </main>
  );
}
