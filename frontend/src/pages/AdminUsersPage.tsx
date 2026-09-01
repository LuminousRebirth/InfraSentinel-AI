import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, jsonBody, type Project, type User, type UserStatus } from "../api/client";
import { ProjectAssignment } from "../components/ProjectAssignment";
import { useI18n } from "../i18n";

export function AdminUsersPage() {
  const { t } = useI18n();
  const [users, setUsers] = useState<User[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [userRows, projectRows] = await Promise.all([api<User[]>("/admin/users?limit=200"), api<Project[]>("/projects")]);
      setUsers(userRows); setProjects(projectRows); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Request failed"); }
  }, []);
  useEffect(() => void load(), [load]);

  async function changeStatus(user: User, status: Exclude<UserStatus, "pending">) {
    if (!window.confirm(t("confirmAction"))) return;
    let rejection_reason: string | undefined;
    if (status === "rejected") rejection_reason = window.prompt(t("rejectionReason")) ?? undefined;
    try {
      await api<User>(`/admin/users/${user.id}/status`, { method: "PATCH", body: jsonBody({ status, rejection_reason }) });
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Request failed"); }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try {
      await api<Project>("/admin/projects", { method: "POST", body: jsonBody({ code: data.get("code"), name: data.get("name") }) });
      event.currentTarget.reset(); await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Request failed"); }
  }

  return (
    <>
      <header className="page-heading"><div><p className="eyebrow">ACCESS CONTROL / USERS</p><h1>{t("users")}</h1></div></header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form className="project-create" onSubmit={createProject}><label>{t("projectCode")}<input name="code" required pattern="[A-Za-z0-9_-]{2,50}" /></label><label>{t("projectName")}<input name="name" required /></label><button className="primary-button">{t("createProject")}</button></form>
      <div className="user-list" role="list">
        {users.map((user) => <article className="user-row" key={user.id} role="listitem">
          <div className="user-identity"><span className={`status-rail ${user.status}`} /><strong>{user.display_name}</strong><small>{user.email} · @{user.username}</small></div>
          <div><span className={`status-badge ${user.status}`}>{t(user.status)}</span><span className="role-badge">{t(user.role)}</span></div>
          <ProjectAssignment user={user} projects={projects} onChanged={() => void load()} />
          <div className="row-actions">{user.status !== "enabled" && <button type="button" onClick={() => void changeStatus(user, "enabled")}>{t("approve")}</button>}{user.status === "pending" && <button type="button" className="danger" onClick={() => void changeStatus(user, "rejected")}>{t("reject")}</button>}{user.status === "enabled" && <button type="button" className="danger" onClick={() => void changeStatus(user, "disabled")}>{t("disable")}</button>}</div>
        </article>)}
      </div>
    </>
  );
}
