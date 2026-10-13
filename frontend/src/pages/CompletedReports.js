import React, { useEffect, useState } from "react";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { Private } from "../context/PrivacyContext";
import { PageHeader, Card, Btn, Badge, Empty, inputCls } from "../components/ui-kit";
import { ManagedSelect } from "../components/ManagedSelect";
import { printSection } from "../lib/print";
import { fmtDate } from "../lib/date";
import { ReceiptText, FileText, FolderArchive, Download, Printer } from "lucide-react";
import { toast } from "sonner";

const TABS = [
  { key: "invoices", path: "completed-invoices", icon: ReceiptText },
  { key: "notes", path: "completed-notes", icon: FileText },
  { key: "packets", path: "completed-packets", icon: FolderArchive },
];

const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);

const presets = {
  day: () => ({ start: today(), end: today() }),
  week: () => ({ start: daysAgo(7), end: today() }),
  month: () => ({ start: daysAgo(30), end: today() }),
};

export default function CompletedReports() {
  const { t } = useLang();
  const [tab, setTab] = useState("invoices");
  const [patients, setPatients] = useState([]);
  const [patientId, setPatientId] = useState("");
  const [preset, setPreset] = useState("month");
  const [start, setStart] = useState(daysAgo(30));
  const [end, setEnd] = useState(today());
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.get("/patients").then((r) => setPatients(r.data)).catch(() => {}); }, []);

  const applyPreset = (p) => {
    setPreset(p);
    if (p !== "custom") { const r = presets[p](); setStart(r.start); setEnd(r.end); }
  };

  const currentTab = TABS.find((x) => x.key === tab);
  const statusOptions = tab === "invoices"
    ? [["paid", t("paid")], ["all", t("allBillingStatuses")], ["unpaid", t("unpaid")], ["denied", t("denied")], ["void", t("void")]]
    : tab === "packets"
    ? [["complete", t("packetComplete")], ["all", t("allBillingStatuses")], ["needs_servicing", t("needsServicing")], ["not_set", t("notSetYet")]]
    : null;

  useEffect(() => { if (statusOptions) setStatus(statusOptions[0][0]); else setStatus(""); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = async () => {
    setLoading(true);
    try {
      const params = { start, end };
      if (patientId) params.patient_id = patientId;
      if (status) params.status = status;
      const r = await api.get(`/reports/${currentTab.path}`, { params });
      setRows(r.data);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [tab, start, end, patientId, status]); // eslint-disable-line react-hooks/exhaustive-deps

  const downloadPdf = async () => {
    try {
      const params = { start, end };
      if (patientId) params.patient_id = patientId;
      if (status) params.status = status;
      const r = await api.get(`/reports/${currentTab.path}/pdf`, { params, responseType: "blob" });
      const url = window.URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${currentTab.path}_report.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { toast.error(apiErr(err)); }
  };

  const patientName = patients.find((p) => p.id === patientId);
  const title = {
    invoices: t("completedInvoicesReport"), notes: t("completedNotesReport"), packets: t("completedPacketsReport"),
  }[tab];

  const billingStatusLabel = {
    unsigned: t("billingStatusUnsigned"), pending_review: t("billingStatusPendingReview"),
    approved: t("billingStatusApproved"), needs_correction: t("billingStatusNeedsCorrection"),
  };
  const servicingLabel = { complete: t("packetComplete"), needs_servicing: t("needsServicing"), not_set: t("notSetYet") };

  return (
    <div>
      <PageHeader title={t("completedWorkReports")} subtitle={t("completedWorkReportsSubtitle")} />

      <div className="flex gap-2 mb-5">
        {TABS.map((tb) => (
          <button key={tb.key} onClick={() => setTab(tb.key)} data-testid={`report-tab-${tb.key}`}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold transition-colors ${tab === tb.key ? "bg-moneygreen-600 text-white" : "bg-white border border-border text-stone-600 hover:bg-tan-50"}`}>
            <tb.icon className="w-4 h-4" />{t(tb.key === "invoices" ? "invoices" : tb.key === "notes" ? "notes" : "claims")}
          </button>
        ))}
      </div>

      <Card className="p-4 mb-5">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("patient")}</label>
            <ManagedSelect listKey="patients" value={patientId} onChange={(e) => setPatientId(e.target.value)}
              className={`${inputCls} mt-1.5`} data-testid="report-patient-filter">
              <option value="">{t("allPatients")}</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </ManagedSelect>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("dateRange")}</label>
            <div className="flex gap-1 mt-1.5">
              {["day", "week", "month", "custom"].map((p) => (
                <button key={p} onClick={() => applyPreset(p)} data-testid={`report-preset-${p}`}
                  className={`px-2.5 py-1.5 rounded-md text-xs font-semibold border ${preset === p ? "bg-moneygreen-600 text-white border-moneygreen-600" : "border-border text-stone-600 hover:bg-tan-50"}`}>
                  {t(p === "day" ? "today" : p === "week" ? "thisWeek" : p === "month" ? "thisMonth" : "customRange")}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("from")}</label>
            <input type="date" value={start} onChange={(e) => { setStart(e.target.value); setPreset("custom"); }} className={`${inputCls} mt-1.5`} data-testid="report-start-date" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("to")}</label>
            <input type="date" value={end} onChange={(e) => { setEnd(e.target.value); setPreset("custom"); }} className={`${inputCls} mt-1.5`} data-testid="report-end-date" />
          </div>
          {statusOptions && (
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("status")}</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={`${inputCls} mt-1.5`} data-testid="report-status-filter">
                {statusOptions.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
              </select>
            </div>
          )}
          <div className="flex gap-2 ml-auto">
            <Btn variant="outline" onClick={downloadPdf} data-testid="report-download-pdf"><Download className="w-4 h-4" />{t("downloadPdf")}</Btn>
            <Btn variant="outline" onClick={() => printSection("report-table")} data-testid="report-print"><Printer className="w-4 h-4" />{t("print")}</Btn>
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div id="report-table" className="p-5">
          <h3 className="font-heading text-lg font-bold text-moneygreen-800 mb-1">{title}</h3>
          <p className="text-xs text-stone-500 mb-4">
            {fmtDate(start)} – {fmtDate(end)} · {patientName ? `${patientName.first_name} ${patientName.last_name}` : t("allPatients")} · {rows.length} {t("records")}
          </p>
          {loading ? <p className="text-sm text-stone-400 py-6 text-center">…</p> : rows.length === 0 ? <Empty text={t("noData")} /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="py-2 pr-3">{t("patient")}</th>
                    <th className="py-2 pr-3">{t("dateOfService")}</th>
                    {tab !== "packets" && <th className="py-2 pr-3">{t("diagnosis")}</th>}
                    {tab === "invoices" && <><th className="py-2 pr-3">{t("cptCode")}</th><th className="py-2 pr-3 text-right">{t("amount")}</th></>}
                    {tab === "notes" && <th className="py-2 pr-3">{t("provider")}</th>}
                    {tab === "packets" && <th className="py-2 pr-3">{t("filename")}</th>}
                    <th className="py-2 pr-3">{t("status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.invoice_id || r.note_id || r.item_id} data-testid={`report-row-${i}`} className="border-b border-border/60">
                      <td className="py-2 pr-3 font-semibold text-moneygreen-800"><Private value={r.patient_name} /></td>
                      <td className="py-2 pr-3 text-stone-600">{fmtDate(r.service_date || r.visit_date)}</td>
                      {tab !== "packets" && <td className="py-2 pr-3 text-stone-600">{r.diagnosis || "—"}</td>}
                      {tab === "invoices" && <><td className="py-2 pr-3 text-stone-600 font-mono text-xs">{r.cpt_code || "—"}</td><td className="py-2 pr-3 text-right font-semibold text-moneygreen-800">${(r.amount || 0).toFixed(2)}</td></>}
                      {tab === "notes" && <td className="py-2 pr-3 text-stone-600">{r.provider || "—"}</td>}
                      {tab === "packets" && <td className="py-2 pr-3 text-stone-500 text-xs">{r.filename}</td>}
                      <td className="py-2 pr-3">
                        {tab === "invoices" && <Badge tone={r.status === "paid" ? "green" : r.status === "void" ? "gray" : "amber"}>{r.status}</Badge>}
                        {tab === "notes" && <Badge tone={r.billing_review_status === "approved" ? "green" : r.billing_review_status === "needs_correction" ? "red" : "amber"}>{billingStatusLabel[r.billing_review_status] || r.billing_review_status}</Badge>}
                        {tab === "packets" && <Badge tone={r.servicing_status === "complete" ? "green" : r.servicing_status === "needs_servicing" ? "red" : "gray"}>{servicingLabel[r.servicing_status] || r.servicing_status}</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
