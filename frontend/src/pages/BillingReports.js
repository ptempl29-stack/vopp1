import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  BarChart, Bar,
} from "recharts";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { usePrivacy, Private } from "../context/PrivacyContext";
import { useSelection, bulkDelete } from "../lib/bulk";
import { PageHeader, Btn, Card, Field, inputCls, Empty } from "../components/ui-kit";
import { Download, DollarSign, CheckCircle2, AlertCircle, FileText, Trash2 } from "lucide-react";
import { toast } from "sonner";

const STATUSES = ["in_transit", "paid", "denied"];
const statusKey = { in_transit: "inTransit", paid: "paid", denied: "denied", unpaid: "unpaid", void: "draft" };

export default function BillingReports() {
  const { t, lang } = useLang();
  const sel = useSelection();
  const [data, setData] = useState(null);
  const [rate, setRate] = useState(60);
  const money = (v) => {
    const n = Number(v || 0);
    return lang === "es"
      ? `RD$ ${(n * rate).toLocaleString("es-DO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [patientId, setPatientId] = useState("");
  const [provider, setProvider] = useState("");
  const [apptType, setApptType] = useState("");
  const [patients, setPatients] = useState([]);
  const [providers, setProviders] = useState([]);

  const statusLabel = (s) => t(statusKey[s] || s);
  const params = () => {
    const p = {};
    if (start) p.start = start;
    if (end) p.end = end;
    if (patientId) p.patient_id = patientId;
    if (provider) p.provider = provider;
    if (apptType) p.appointment_type = apptType;
    return p;
  };
  const load = () => api.get("/reports/billing", { params: params() }).then((r) => setData(r.data)).catch((e) => toast.error(apiErr(e)));
  useEffect(() => {
    load();
    api.get("/public/settings").then((r) => { if (r.data?.usd_to_dop) setRate(Number(r.data.usd_to_dop)); }).catch(() => {});
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/users").then((r) => setProviders(r.data.filter((u) => ["doctor", "psychologist", "nurse", "admin"].includes(u.role)))).catch(() => {});
  }, []);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [patientId, provider, apptType]);

  const exportCsv = async () => {
    try {
      const res = await api.get("/reports/billing/export", { params: params(), responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "billing_report.csv";
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { toast.error(apiErr(err)); }
  };

  const changeStatus = async (id, status) => {
    try { await api.put(`/invoices/${id}/status`, null, { params: { status } }); toast.success(t("updated")); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };
  const removeInvoice = async (id) => {
    try { await api.delete(`/invoices/${id}`); load(); } catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    try { await bulkDelete("/invoices/bulk-delete", [...sel.selected], t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const s = data?.summary;
  const invoices = data?.invoices || [];
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
          <Field label={t("byPatient")}>
            <select value={patientId} onChange={(e) => setPatientId(e.target.value)} className={inputCls + " !w-auto"} data-testid="report-filter-patient">
              <option value="">{t("allPatients")}</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </Field>
          <Field label={t("byDoctor")}>
            <select value={provider} onChange={(e) => setProvider(e.target.value)} className={inputCls + " !w-auto"} data-testid="report-filter-doctor">
              <option value="">{t("allDoctors")}</option>
              {providers.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
            </select>
          </Field>
          <Field label={t("byAppointmentType")}>
            <select value={apptType} onChange={(e) => setApptType(e.target.value)} className={inputCls + " !w-auto"} data-testid="report-filter-appt-type">
              <option value="">{t("allTypes")}</option>
              <option value="in_person">{t("inPerson")}</option>
              <option value="telehealth">{t("telehealth")}</option>
            </select>
          </Field>
          <Field label={t("from")}>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputCls} data-testid="report-start" />
          </Field>
          <Field label={t("to")}>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={inputCls} data-testid="report-end" />
          </Field>
          <Btn onClick={load} data-testid="apply-filter-btn">{t("applyFilter")}</Btn>
          <Btn variant="outline" onClick={() => { setStart(""); setEnd(""); setPatientId(""); setProvider(""); setApptType(""); setTimeout(load, 0); }} data-testid="clear-report-filter">{t("clearFilter")}</Btn>
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
                    {c.value == null ? "—" : c.money === false ? c.value : money(c.value)}
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
                <YAxis tick={{ fontSize: 11 }} stroke="#5C6661" tickFormatter={money} />
                <Tooltip formatter={(val) => money(val)} />
                <Area type="monotone" dataKey="billed" stroke="#C9BC9E" fill="none" name={t("billed")} />
                <Area type="monotone" dataKey="collected" stroke="#2D5A40" fill="url(#gCollected)" name={t("collected")} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <Empty text={t("noData")} />}
        </Card>

        <Card className="p-5">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-4">{t("revenueByPatient")}</h3>
          {data?.patient_breakdown?.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.patient_breakdown.slice(0, 8)} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D9" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="#5C6661" tickFormatter={money} />
                <YAxis type="category" dataKey="patient" tick={{ fontSize: 11 }} width={110} stroke="#5C6661" />
                <Tooltip formatter={(val) => money(val)} />
                <Bar dataKey="revenue" fill="#41805B" radius={[0, 4, 4, 0]} name={t("revenue")} />
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty text={t("noData")} />}
        </Card>
      </div>

      {/* Invoices with select / status / delete */}
      <div className="mt-6">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h3 className="font-heading text-lg font-bold text-moneygreen-800">{t("invoices")}</h3>
          {invoices.length > 0 && (
            <div className="ml-auto flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-sm text-stone-600 cursor-pointer">
                <input type="checkbox" data-testid="select-all-report-invoices"
                  checked={sel.count >= invoices.length && invoices.length > 0}
                  onChange={() => sel.toggleAll(invoices.map((v) => v.id))}
                  className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                {t("selectAll")}
              </label>
              {sel.count > 0 && (<>
                <span className="text-sm text-stone-500">{sel.count}</span>
                <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-report-invoices"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
                <Btn variant="outline" onClick={sel.clear} data-testid="deselect-report-invoices">{t("deselectAll")}</Btn>
              </>)}
            </div>
          )}
        </div>
        <Card className="overflow-hidden">
          {invoices.length === 0 ? <p className="p-6 text-sm text-stone-400">{t("noData")}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="px-4 py-3 w-8"></th>
                    <th className="px-5 py-3">{t("invoiceNumber")}</th>
                    <th className="px-5 py-3">{t("patient")}</th>
                    <th className="px-5 py-3 hidden md:table-cell">{t("serviceDate")}</th>
                    <th className="px-5 py-3">{t("status")}</th>
                    <th className="px-5 py-3 text-right">{t("total")}</th>
                    <th className="px-5 py-3 text-right">{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((v, i) => (
                    <tr key={v.id} data-testid={`report-invoice-${v.id}`} className={`border-b border-border/60 ${sel.has(v.id) ? "bg-moneygreen-50" : i % 2 ? "bg-tan-50/40" : ""}`}>
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={sel.has(v.id)} onChange={() => sel.toggle(v.id)}
                          data-testid={`select-report-invoice-${v.id}`} className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                      </td>
                      <td className="px-5 py-3 font-mono font-semibold text-moneygreen-700">{v.invoice_number || "—"}</td>
                      <td className="px-5 py-3 text-stone-700"><Private value={v.patient_name} /></td>
                      <td className="px-5 py-3 hidden md:table-cell text-stone-600">{v.service_date}</td>
                      <td className="px-5 py-3">
                        <select value={STATUSES.includes(v.status) ? v.status : "in_transit"} onChange={(e) => changeStatus(v.id, e.target.value)}
                          data-testid={`report-invoice-status-${v.id}`}
                          className="px-2 py-1 rounded-md border border-border text-xs font-semibold cursor-pointer bg-white focus:outline-none focus:ring-2 focus:ring-moneygreen-500">
                          {STATUSES.map((st) => <option key={st} value={st}>{statusLabel(st)}</option>)}
                        </select>
                      </td>
                      <td className="px-5 py-3 text-right font-semibold text-moneygreen-800">{money(v.total)}</td>
                      <td className="px-5 py-3 text-right">
                        <Btn variant="ghost" onClick={() => removeInvoice(v.id)} data-testid={`delete-report-invoice-${v.id}`} className="!px-2 !text-destructive" title={t("delete")}><Trash2 className="w-4 h-4" /></Btn>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
