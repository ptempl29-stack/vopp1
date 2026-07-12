import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  BarChart, Bar,
} from "recharts";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Btn, Card, Field, inputCls, Empty } from "../components/ui-kit";
import { Download, DollarSign, CheckCircle2, AlertCircle, FileText } from "lucide-react";
import { toast } from "sonner";

export default function BillingReports() {
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const load = () => {
    const params = {};
    if (start) params.start = start;
    if (end) params.end = end;
    api.get("/reports/billing", { params }).then((r) => setData(r.data)).catch((e) => toast.error(apiErr(e)));
  };
  useEffect(() => { load(); }, []);

  const exportCsv = () => {
    const token = localStorage.getItem("vpp_token");
    const qs = new URLSearchParams();
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);
    qs.set("auth", token);
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/reports/billing/export?${qs.toString()}`, "_blank");
  };

  const s = data?.summary;
  const cards = [
    { key: "totalBilled", value: s?.total_billed, icon: DollarSign, tone: "moneygreen-600" },
    { key: "collected", value: s?.collected, icon: CheckCircle2, tone: "moneygreen-500" },
    { key: "outstanding", value: s?.outstanding, icon: AlertCircle, tone: "tan-400" },
    { key: "invoicesLabel", value: s?.invoice_count, icon: FileText, tone: "stone-500", money: false },
  ];

  return (
    <div>
      <PageHeader title={t("reports")}
        action={<Btn onClick={exportCsv} data-testid="export-csv-btn"><Download className="w-4 h-4" />{t("exportCsv")}</Btn>} />

      <Card className="p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("dateRange") + " (" + t("from") + ")"}>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputCls} data-testid="report-start" />
          </Field>
          <Field label={t("to")}>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={inputCls} data-testid="report-end" />
          </Field>
          <Btn onClick={load} data-testid="apply-filter-btn">{t("applyFilter")}</Btn>
          <Btn variant="outline" onClick={() => { setStart(""); setEnd(""); setTimeout(load, 0); }}>{t("clearFilter")}</Btn>
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {cards.map((c, i) => (
          <motion.div key={c.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <Card className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t(c.key)}</p>
                  <p className="font-heading text-3xl font-extrabold text-moneygreen-800 mt-2" data-testid={`report-${c.key}`}>
                    {c.value == null ? "—" : c.money === false ? c.value : `$${Number(c.value).toFixed(2)}`}
                  </p>
                </div>
                <div className={`w-11 h-11 rounded-md bg-${c.tone} flex items-center justify-center`}>
                  <c.icon className="w-5 h-5 text-white" />
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-4">{t("revenueOverTime")}</h3>
          {data?.timeseries?.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={data.timeseries}>
                <defs>
                  <linearGradient id="gCollected" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2D5A40" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#2D5A40" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D9" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#5C6661" />
                <YAxis tick={{ fontSize: 11 }} stroke="#5C6661" />
                <Tooltip />
                <Area type="monotone" dataKey="billed" stroke="#C9BC9E" fill="none" name={t("billed")} />
                <Area type="monotone" dataKey="collected" stroke="#2D5A40" fill="url(#gCollected)" name={t("collected")} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <Empty text={t("noData")} />}
        </Card>

        <Card className="p-5">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-4">{t("byCptCode")}</h3>
          {data?.cpt_breakdown?.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.cpt_breakdown.slice(0, 8)} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D9" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="#5C6661" />
                <YAxis type="category" dataKey="cpt_code" tick={{ fontSize: 11 }} width={60} stroke="#5C6661" />
                <Tooltip />
                <Bar dataKey="revenue" fill="#41805B" radius={[0, 4, 4, 0]} name={t("revenue")} />
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty text={t("noData")} />}
        </Card>
      </div>

      {data?.cpt_breakdown?.length > 0 && (
        <Card className="mt-4 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("cptCode")}</th>
                  <th className="px-5 py-3">{t("description")}</th>
                  <th className="px-5 py-3 text-right">{t("count")}</th>
                  <th className="px-5 py-3 text-right">{t("revenue")}</th>
                </tr>
              </thead>
              <tbody>
                {data.cpt_breakdown.map((c, i) => (
                  <tr key={c.cpt_code} className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3 font-mono font-semibold text-moneygreen-700">{c.cpt_code}</td>
                    <td className="px-5 py-3 text-stone-600">{c.description}</td>
                    <td className="px-5 py-3 text-right text-stone-600">{c.count}</td>
                    <td className="px-5 py-3 text-right font-semibold text-moneygreen-800">${c.revenue.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
