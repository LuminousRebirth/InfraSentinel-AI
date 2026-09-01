import { useSyncExternalStore } from "react";

import type { Locale } from "../api/client";

const zhCN = {
  brand: "InfraSentinel",
  tagline: "基础设施智能巡检哨兵",
  login: "登录",
  register: "申请账户",
  logout: "退出",
  identifier: "邮箱或用户名",
  email: "邮箱",
  username: "用户名",
  displayName: "显示名称",
  password: "密码",
  passwordHint: "至少 6 个字符",
  showPassword: "显示密码",
  hidePassword: "隐藏密码",
  noAccount: "还没有账户？",
  hasAccount: "已有账户？",
  pendingTitle: "账户正在等待审核",
  pendingBody: "管理员批准后即可进入巡检工作台。",
  disabledTitle: "账户已停用",
  rejectedTitle: "账户申请未通过",
  home: "巡检台",
  users: "用户与权限",
  audit: "审计轨迹",
  role: "角色",
  status: "状态",
  projects: "项目范围",
  welcome: "值守概览",
  systemOnline: "身份服务在线",
  pipelinePath: "巡检路径",
  profile: "当前身份",
  approve: "批准",
  reject: "拒绝",
  disable: "停用",
  rejectionReason: "拒绝原因",
  assign: "分配",
  remove: "移除",
  projectCode: "项目编码",
  projectName: "项目名称",
  createProject: "新建项目",
  action: "动作",
  actor: "操作者",
  target: "目标",
  result: "结果",
  time: "时间",
  details: "变更详情",
  filterAction: "按动作筛选",
  loadMore: "加载更早记录",
  loading: "正在同步…",
  retry: "重试",
  save: "保存",
  language: "语言",
  pending: "待审核",
  enabled: "已启用",
  disabled: "已停用",
  rejected: "已拒绝",
  admin: "管理员",
  user: "用户",
  success: "成功",
  failure: "失败",
  empty: "暂无记录",
  confirmAction: "确认执行此操作？",
  sessionChecking: "正在校验会话…",
} as const;

const en: Record<keyof typeof zhCN, string> = {
  brand: "InfraSentinel",
  tagline: "Intelligent infrastructure inspection sentinel",
  login: "Sign in",
  register: "Request access",
  logout: "Sign out",
  identifier: "Email or username",
  email: "Email",
  username: "Username",
  displayName: "Display name",
  password: "Password",
  passwordHint: "At least 6 characters",
  showPassword: "Show password",
  hidePassword: "Hide password",
  noAccount: "Need an account?",
  hasAccount: "Already registered?",
  pendingTitle: "Account awaiting review",
  pendingBody: "You can enter the inspection workspace after administrator approval.",
  disabledTitle: "Account disabled",
  rejectedTitle: "Account request rejected",
  home: "Inspection desk",
  users: "Users & access",
  audit: "Audit trail",
  role: "Role",
  status: "Status",
  projects: "Project scope",
  welcome: "Watch overview",
  systemOnline: "Identity service online",
  pipelinePath: "Inspection path",
  profile: "Current identity",
  approve: "Approve",
  reject: "Reject",
  disable: "Disable",
  rejectionReason: "Rejection reason",
  assign: "Assign",
  remove: "Remove",
  projectCode: "Project code",
  projectName: "Project name",
  createProject: "Create project",
  action: "Action",
  actor: "Actor",
  target: "Target",
  result: "Result",
  time: "Time",
  details: "Change details",
  filterAction: "Filter by action",
  loadMore: "Load earlier records",
  loading: "Synchronizing…",
  retry: "Retry",
  save: "Save",
  language: "Language",
  pending: "Pending",
  enabled: "Enabled",
  disabled: "Disabled",
  rejected: "Rejected",
  admin: "Administrator",
  user: "User",
  success: "Success",
  failure: "Failure",
  empty: "No records",
  confirmAction: "Confirm this action?",
  sessionChecking: "Checking session…",
};

export const messages = { "zh-CN": zhCN, en } as const;
export type MessageKey = keyof typeof zhCN;

const listeners = new Set<() => void>();

export function getLocale(): Locale {
  const stored = localStorage.getItem("infrasentinel.locale");
  return stored === "en" ? "en" : "zh-CN";
}

export function setLocale(locale: Locale): void {
  localStorage.setItem("infrasentinel.locale", locale);
  document.documentElement.lang = locale;
  listeners.forEach((listener) => listener());
}

export function t(key: MessageKey, locale = getLocale()): string {
  return messages[locale][key];
}

export function useI18n() {
  const locale = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getLocale,
    () => "zh-CN" as Locale,
  );
  return { locale, setLocale, t: (key: MessageKey) => t(key, locale) };
}
