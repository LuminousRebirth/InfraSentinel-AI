import { useState } from "react";

import { api, type Project, type User } from "../api/client";
import { useI18n } from "../i18n";

export function ProjectAssignment({ user, projects, onChanged }: { user: User; projects: Project[]; onChanged: () => void }) {
  const { t } = useI18n();
  const [error, setError] = useState("");
  const assigned = new Set(user.projects.map((project) => project.id));
  async function toggle(project: Project) {
    const remove = assigned.has(project.id);
    if (!window.confirm(t("confirmAction"))) return;
    try {
      await api<void>(`/admin/users/${user.id}/projects/${project.id}`, { method: remove ? "DELETE" : "PUT" });
      setError("");
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed");
    }
  }
  return (
    <div className="assignment-list">
      {projects.map((project) => <button type="button" className={assigned.has(project.id) ? "assigned" : ""} key={project.id} onClick={() => void toggle(project)}><code>{project.code}</code><span>{assigned.has(project.id) ? t("remove") : t("assign")}</span></button>)}
      {error && <span className="inline-error" role="alert">{error}</span>}
    </div>
  );
}
