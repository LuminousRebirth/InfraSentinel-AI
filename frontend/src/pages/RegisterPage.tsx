import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { useSession } from "../auth/session";
import { useI18n } from "../i18n";

export function RegisterPage({ switcher }: { switcher: ReactNode }) {
  const { register } = useSession();
  const { locale, t } = useI18n();
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await register({
        email: String(data.email), username: String(data.username),
        display_name: String(data.display_name), password: String(data.password), locale,
      });
      navigate("/pending", { replace: true, state: { registered: true } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed");
    } finally { setBusy(false); }
  }

  return (
    <main className="auth-layout">
      <section className="auth-context compact">
        <div className="auth-brand"><span className="brand-mark">IS</span><strong>{t("brand")}</strong></div>
        <p className="eyebrow">IDENTITY ONBOARDING / 02</p><h1>{t("register")}</h1>
        <div className="route-diagram" aria-hidden="true"><span className="route-node active">01</span><i /><span className="route-node active">02</span><i /><span className="route-node">03</span></div>
      </section>
      <section className="auth-panel">
        <div className="auth-panel-top">{switcher}</div>
        <form onSubmit={submit}>
          <p className="eyebrow">ACCESS REQUEST</p><h2>{t("register")}</h2>
          <label>{t("email")}<input name="email" type="email" autoComplete="email" required /></label>
          <label>{t("username")}<input name="username" pattern="[a-z0-9._-]{3,32}" autoComplete="username" required /></label>
          <label>{t("displayName")}<input name="display_name" autoComplete="name" required /></label>
          <label>{t("password")}<small>{t("passwordHint")}</small><span className="password-field"><input name="password" type={visible ? "text" : "password"} minLength={6} autoComplete="new-password" required /><button type="button" onClick={() => setVisible(!visible)}>{visible ? t("hidePassword") : t("showPassword")}</button></span></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" disabled={busy}>{busy ? t("loading") : t("register")}</button>
          <p className="form-foot">{t("hasAccount")} <Link to="/login">{t("login")}</Link></p>
        </form>
      </section>
    </main>
  );
}
