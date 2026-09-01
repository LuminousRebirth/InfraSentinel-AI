import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { useSession } from "../auth/session";
import { useI18n } from "../i18n";

export function LoginPage({ switcher }: { switcher: ReactNode }) {
  const { login } = useSession();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const user = await login(String(data.get("identifier")), String(data.get("password")));
      navigate(user.status === "enabled" ? "/app" : "/pending", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-context" aria-label={t("pipelinePath")}>
        <div className="auth-brand"><span className="brand-mark">IS</span><strong>{t("brand")}</strong></div>
        <p className="eyebrow">INFRASTRUCTURE WATCH / 01</p>
        <h1>{t("tagline")}</h1>
        <div className="route-diagram" aria-hidden="true">
          <span className="route-node active">01</span><i /><span className="route-node">02</span><i /><span className="route-node">03</span>
        </div>
        <p className="status-line"><span />{t("systemOnline")}</p>
      </section>
      <section className="auth-panel">
        <div className="auth-panel-top">{switcher}</div>
        <form onSubmit={submit}>
          <p className="eyebrow">ACCESS GATEWAY</p>
          <h2>{t("login")}</h2>
          <label>{t("identifier")}<input name="identifier" autoComplete="username" required minLength={3} /></label>
          <label>{t("password")}
            <span className="password-field"><input name="password" type={visible ? "text" : "password"} autoComplete="current-password" required /><button type="button" onClick={() => setVisible(!visible)}>{visible ? t("hidePassword") : t("showPassword")}</button></span>
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" disabled={busy}>{busy ? t("loading") : t("login")}</button>
          <p className="form-foot">{t("noAccount")} <Link to="/register">{t("register")}</Link></p>
        </form>
      </section>
    </main>
  );
}
