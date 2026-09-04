import { Navigate, NavLink, Outlet, Route, Routes } from "react-router";

import { useSession } from "./auth/session";
import { useI18n } from "./i18n";
import { AdminAuditPage } from "./pages/AdminAuditPage";
import { AdminIntelligencePage } from "./pages/AdminIntelligencePage";
import { AdminLifecyclePage } from "./pages/AdminLifecyclePage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AppHomePage } from "./pages/AppHomePage";
import { DetectionDetailPage } from "./pages/DetectionDetailPage";
import { DetectionHistoryPage } from "./pages/DetectionHistoryPage";
import { DetectionPage } from "./pages/DetectionPage";
import { LoginPage } from "./pages/LoginPage";
import { PendingPage } from "./pages/PendingPage";
import { RegisterPage } from "./pages/RegisterPage";
import "./styles/app.css";
import "./styles/auth.css";
import "./styles/detection.css";
import "./styles/intelligence.css";
import "./styles/intelligence-workflow.css";
import "./styles/intelligence-rules.css";
import "./styles/lifecycle.css";

function LanguageSwitch() {
  const { locale, setLocale, t } = useI18n();
  return (
    <button
      className="language-switch"
      type="button"
      onClick={() => setLocale(locale === "zh-CN" ? "en" : "zh-CN")}
      aria-label={t("language")}
    >
      {locale === "zh-CN" ? "EN" : "中文"}
    </button>
  );
}

function RequireEnabled({ admin = false }: { admin?: boolean }) {
  const { user, loading } = useSession();
  const { t } = useI18n();
  if (loading) return <div className="center-message">{t("sessionChecking")}</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.status !== "enabled") return <Navigate to="/pending" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/app" replace />;
  return <Outlet />;
}

function AppShell() {
  const { user, logout } = useSession();
  const { t } = useI18n();
  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink className="brand-lockup" to="/app">
          <span className="brand-mark" aria-hidden="true">IS</span>
          <span><strong>{t("brand")}</strong><small>{t("tagline")}</small></span>
        </NavLink>
        <nav aria-label="Primary">
          <NavLink to="/app">{t("home")}</NavLink>
          <NavLink to="/detections">{t("detection")}</NavLink>
          <NavLink to="/detections/history">{t("history")}</NavLink>
          <NavLink to="/alerts">{t("alerts")}</NavLink>
          {user?.role === "admin" && <NavLink to="/admin/users">{t("users")}</NavLink>}
          {user?.role === "admin" && <NavLink to="/admin/audit">{t("audit")}</NavLink>}
          {user?.role === "admin" && <NavLink to="/admin/intelligence">{t("modelSettings")}</NavLink>}
          {user?.role === "admin" && <NavLink to="/admin/lifecycle">{t("dataModels")}</NavLink>}
        </nav>
        <div className="topbar-actions">
          <LanguageSwitch />
          <span className="identity-chip">{user?.display_name}</span>
          <button className="quiet-button" type="button" onClick={() => void logout()}>{t("logout")}</button>
        </div>
      </header>
      <main className="workspace"><Outlet /></main>
    </div>
  );
}

function RootRedirect() {
  const { user, loading } = useSession();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.status === "enabled" ? "/app" : "/pending"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage switcher={<LanguageSwitch />} />} />
      <Route path="/register" element={<RegisterPage switcher={<LanguageSwitch />} />} />
      <Route path="/pending" element={<PendingPage switcher={<LanguageSwitch />} />} />
      <Route element={<RequireEnabled />}>
        <Route element={<AppShell />}>
          <Route path="/app" element={<AppHomePage />} />
          <Route path="/detections" element={<DetectionPage />} />
          <Route path="/detections/history" element={<DetectionHistoryPage />} />
          <Route path="/detections/:id" element={<DetectionDetailPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route element={<RequireEnabled admin />}>
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/audit" element={<AdminAuditPage />} />
            <Route path="/admin/intelligence" element={<AdminIntelligencePage />} />
            <Route path="/admin/lifecycle" element={<AdminLifecyclePage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
