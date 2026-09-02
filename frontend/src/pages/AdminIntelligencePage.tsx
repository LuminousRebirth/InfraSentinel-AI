import { type FormEvent, useEffect, useState } from "react";

import { createProvider, createRule, getProviders, getRules, replaceRule, saveCredential, type AlertRule, type Provider } from "../api/intelligence";
import { ApiError } from "../api/client";
import { useI18n } from "../i18n";

export function AdminIntelligencePage() {
  const { t } = useI18n();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    try {
      const [providerItems, ruleItems] = await Promise.all([getProviders(), getRules()]);
      setProviders(providerItems);
      setRules(ruleItems);
      setSelectedProvider((current) => current || providerItems[0]?.id || "");
    } catch (reason) {
      setMessage(reason instanceof ApiError ? reason.message : "加载失败");
    }
  }
  useEffect(() => { void load(); }, []);

  async function addProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await createProvider({
        code: String(form.get("code")), provider: String(form.get("provider")),
        endpoint: String(form.get("endpoint")), model_name: String(form.get("model_name")),
        supports_vision: true, timeout_seconds: 60, max_retries: 2, enabled: true,
        is_default: providers.length === 0,
      });
      event.currentTarget.reset();
      setMessage(t("saved"));
      await load();
    } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : "保存失败"); }
  }

  async function storeKey() {
    if (!selectedProvider || !apiKey) return;
    try {
      await saveCredential(selectedProvider, apiKey, true);
      setApiKey("");
      setMessage(t("credentialSaved"));
    } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : "保存失败"); }
  }

  async function addRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const className = String(form.get("class_name")).trim();
    try {
      await createRule({ code: `custom-${className.toLowerCase()}-${Date.now()}`, name_zh: String(form.get("name_zh")), name_en: String(form.get("name_en")), project_id: null, class_name: className, min_confidence: Number(form.get("min_confidence")), risk_level: String(form.get("risk_level")), merge_window_ms: 3000, iou_threshold: 0.3, cooldown_seconds: 60, priority: 200, enabled: true });
      event.currentTarget.reset();
      await load();
    } catch (reason) { setMessage(reason instanceof ApiError ? reason.message : "规则保存失败"); }
  }

  async function toggleRule(rule: AlertRule) {
    try { await replaceRule(rule, { enabled: !rule.enabled }); await load(); }
    catch (reason) { setMessage(reason instanceof ApiError ? reason.message : "规则保存失败"); }
  }

  return <section className="intelligence-admin">
    <header className="alert-heading"><div><span className="section-kicker">CONTROL PLANE</span><h1>{t("intelligenceSettings")}</h1></div></header>
    {message && <p className="notice-strip" role="status">{message}</p>}
    <div className="settings-grid">
      <section className="settings-card"><h2>{t("modelProviders")}</h2>
        <form className="provider-form" onSubmit={(event) => void addProvider(event)}>
          <label>代号<input required name="code" placeholder="qwen-vl" /></label>
          <label>供应商<select name="provider"><option value="qwen">Qwen</option><option value="deepseek">DeepSeek</option><option value="glm">GLM</option></select></label>
          <label className="wide">API 地址<input required name="endpoint" placeholder="https://example.com/v1" /></label>
          <label className="wide">视觉模型<input required name="model_name" placeholder="vision-model" /></label>
          <button type="submit">{t("addProvider")}</button>
        </form>
        <div className="provider-list">{providers.map((item) => <div key={item.id}><strong>{item.code}</strong><span>{item.provider} · {item.model_name}</span></div>)}</div>
      </section>
      <section className="settings-card"><h2>{t("systemCredential")}</h2><p>{t("credentialHint")}</p>
        <label>供应商<select value={selectedProvider} onChange={(event) => setSelectedProvider(event.target.value)}>{providers.map((item) => <option value={item.id} key={item.id}>{item.code}</option>)}</select></label>
        <label>API Key<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>
        <button type="button" disabled={!selectedProvider || apiKey.length < 8} onClick={() => void storeKey()}>{t("saveCredential")}</button>
      </section>
    </div>
    <section className="rule-matrix"><div><h2>{t("alertRules")}</h2><span>{rules.length} rules</span></div>
      <form className="rule-form" onSubmit={(event) => void addRule(event)}><input required name="class_name" placeholder="类别，如 corrosion" /><input required name="name_zh" placeholder="中文名称" /><input required name="name_en" placeholder="English name" /><input required name="min_confidence" type="number" min="0" max="1" step="0.01" defaultValue="0.5" /><select name="risk_level"><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select><button type="submit">{t("addRule")}</button></form>
      <table><thead><tr><th>类别</th><th>风险</th><th>置信度</th><th>合并窗口</th><th>状态</th></tr></thead><tbody>{rules.map((rule) => <tr key={rule.id}><td><strong>{rule.class_name}</strong><small>{rule.name_zh}</small></td><td><span className={`level-stamp ${rule.risk_level}`}>{rule.risk_level}</span></td><td>{Math.round(rule.min_confidence * 100)}%</td><td>{rule.merge_window_ms / 1000}s</td><td><button className="text-button" type="button" onClick={() => void toggleRule(rule)}>{rule.enabled ? "启用" : "停用"}</button></td></tr>)}</tbody></table>
    </section>
  </section>;
}
