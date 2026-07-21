import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import api from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Card, Badge, Empty, Btn, inputCls } from "../components/ui-kit";
import { fmtDateTime } from "../lib/date";
import { ShieldCheck, ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";

const PAGE = 25;

const actionTone = {
  view: "gray", create: "green", update: "amber", delete: "red",
  login_success: "green", login_failed: "red",
};

const resources = ["", "patient", "note", "invoice", "form", "auth"];
const actions = ["", "view", "create", "update", "delete", "login_success", "login_failed"];

export default function AuditLog() {
  const { t } = useLang();
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [f, setF] = useState({ resource: "", action: "", start: "", end: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: PAGE, skip: page * PAGE };
      if (f.resource) params.resource = f.resource;
      if (f.action) params.action = f.action;
      if (f.start) params.start = f.start;
      if (f.end) params.end = f.end;
      const r = await api.get("/audit", { params });
      setData(r.data);
    } catch { /* handled globally */ }
    finally { setLoading(false); }
  }, [page, f]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (k) => (e) => { setPage(0); setF({ ...f, [k]: e.target.value }); };
  const reset = () => { setPage(0); setF({ resource: "", action: "", start: "", end: "" }); };

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE));
  const fmt = (iso) => fmtDateTime(iso);

  return (
    <div data-testid="audit-page">
      <PageHeader title={t("auditLog")} subtitle={`${data.total} ${t("auditEntries")}`}
        action={<Btn variant="outline" onClick={reset} data-testid="audit-reset"><RotateCcw className="w-4 h-4" />{t("reset")}</Btn>} />

      <Card className="p-4 mb-4 no-print">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="text-xs font-semibold text-stone-500">{t("resource")}</label>
            <select value={f.resource} onChange={setFilter("resource")} className={inputCls} data-testid="audit-filter-resource">
              {resources.map((r) => <option key={r} value={r}>{r ? t(`res_${r}`) : t("all")}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-stone-500">{t("action")}</label>
            <select value={f.action} onChange={setFilter("action")} className={inputCls} data-testid="audit-filter-action">
              {actions.map((a) => <option key={a} value={a}>{a ? t(`act_${a}`) : t("all")}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-stone-500">{t("from")}</label>
            <input type="date" value={f.start} onChange={setFilter("start")} className={inputCls} data-testid="audit-filter-start" />
          </div>
          <div>
            <label className="text-xs font-semibold text-stone-500">{t("to")}</label>
            <input type="date" value={f.end} onChange={setFilter("end")} className={inputCls} data-testid="audit-filter-end" />
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        {data.items.length === 0 ? <Empty text={loading ? "…" : t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("timestamp")}</th>
                  <th className="px-5 py-3">{t("actor")}</th>
                  <th className="px-5 py-3">{t("action")}</th>
                  <th className="px-5 py-3">{t("resource")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("details")}</th>
                  <th className="px-5 py-3 hidden lg:table-cell">IP</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it, i) => (
                  <motion.tr key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.01 }}
                    data-testid={`audit-row-${it.id}`}
                    className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3 font-mono text-xs text-stone-600 whitespace-nowrap">{fmt(it.created_at)}</td>
                    <td className="px-5 py-3">
                      <span className="font-semibold text-moneygreen-800">{it.actor_name || "—"}</span>
                      {it.actor_role && <span className="ml-1 text-xs text-stone-400 capitalize">({it.actor_role})</span>}
                    </td>
                    <td className="px-5 py-3"><Badge tone={actionTone[it.action] || "gray"}>{t(`act_${it.action}`)}</Badge></td>
                    <td className="px-5 py-3 text-stone-600">{t(`res_${it.resource}`)}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-500 max-w-xs truncate">{it.detail || "—"}</td>
                    <td className="px-5 py-3 hidden lg:table-cell font-mono text-xs text-stone-400">{it.ip || "—"}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="flex items-center justify-between mt-4 no-print">
        <p className="text-xs text-stone-500">{t("page")} {page + 1} / {totalPages}</p>
        <div className="flex gap-2">
          <Btn variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)} data-testid="audit-prev"><ChevronLeft className="w-4 h-4" />{t("prev")}</Btn>
          <Btn variant="outline" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)} data-testid="audit-next">{t("next")}<ChevronRight className="w-4 h-4" /></Btn>
        </div>
      </div>
    </div>
  );
}
