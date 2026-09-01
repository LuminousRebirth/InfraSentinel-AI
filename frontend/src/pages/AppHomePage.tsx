import { useSession } from "../auth/session";
import { useI18n } from "../i18n";

export function AppHomePage() {
  const { user } = useSession();
  const { t } = useI18n();
  const projects = user?.projects ?? [];
  return (
    <>
      <header className="page-heading"><div><p className="eyebrow">OPERATIONS / WATCH</p><h1>{t("welcome")}</h1></div><span className="online-pill"><i />{t("systemOnline")}</span></header>
      <section className="inspection-grid">
        <article className="route-card">
          <div className="section-label"><span>01</span>{t("pipelinePath")}</div>
          <div className="pipeline-map" aria-label={t("pipelinePath")}>
            <div className="pipeline-segment active"><span>IDENTITY</span><i /></div>
            <div className="pipeline-segment active"><span>ACCESS</span><i /></div>
            <div className="pipeline-segment"><span>INSPECTION</span><i /></div>
            <div className="pipeline-segment"><span>REPORT</span><i /></div>
          </div>
        </article>
        <article className="identity-card"><div className="section-label"><span>02</span>{t("profile")}</div><dl><div><dt>{t("displayName")}</dt><dd>{user?.display_name}</dd></div><div><dt>{t("role")}</dt><dd>{user && t(user.role)}</dd></div><div><dt>{t("status")}</dt><dd className="cyan-text">{user && t(user.status)}</dd></div></dl></article>
        <article className="projects-card"><div className="section-label"><span>03</span>{t("projects")}</div>{projects.length ? <ul>{projects.map((project) => <li key={project.id}><code>{project.code}</code><span>{project.name}</span><i className="health-dot" /></li>)}</ul> : <p className="empty-state">{t("empty")}</p>}</article>
      </section>
    </>
  );
}
