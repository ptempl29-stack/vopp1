import React, { useEffect, useState } from "react";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { Letterhead } from "../components/Letterhead";
import { PageHeader, Btn, Card, Badge, inputCls } from "../components/ui-kit";
import { Plus, Trash2, FilePlus2, Save, FileDown, Printer, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

let seq = 0;
const newItem = () => ({ _uid: `it-${seq++}`, cpt_code: "", description: "", quantity: 1, minutes: 15, amount: 0 });
const emptyInvoice = {
  patient_id: "", patient_name: "", dob: "", ssn: "", policy_number: "", gender: "",
  invoice_number: "", service_date: new Date().toISOString().slice(0, 10),
  visit_reason: "", icd10: "", provider: "", status: "unpaid",
};
const reasons = ["General Consultation", "Physical Therapy", "Therapeutic Massage", "Relaxing Massage", "Evaluation", "Follow-up", "Re-evaluation", "Psychotherapy", "Group Therapy"];

const cellCls = "w-full px-2 py-1.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm";

export default function Invoices() {
  const { t } = useLang();
  const [settings, setSettings] = useState(null);
  const [patients, setPatients] = useState([]);
  const [cpt, setCpt] = useState([]);
  const [providers, setProviders] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [inv, setInv] = useState(emptyInvoice);
  const [items, setItems] = useState([newItem()]);

  const loadInvoices = () => api.get("/invoices").then((r) => setInvoices(r.data)).catch(() => {});
  const loadNumber = () => api.get("/invoices/next-number").then((r) => setInv((s) => ({ ...s, invoice_number: r.data.invoice_number }))).catch(() => {});

  useEffect(() => {
    api.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/cpt-codes").then((r) => setCpt(r.data)).catch(() => {});
    api.get("/users").then((r) => setProviders(r.data.filter((u) => ["doctor", "psychologist", "nurse"].includes(u.role)))).catch(() => {});
    loadInvoices();
    loadNumber();
  }, []);

  const onPatient = (e) => {
    const p = patients.find((x) => x.id === e.target.value);
    setInv((s) => ({
      ...s, patient_id: e.target.value,
      patient_name: p ? `${p.first_name} ${p.last_name}` : "",
      dob: p?.dob || s.dob, gender: p?.gender || s.gender,
    }));
  };
  const setF = (k) => (e) => setInv({ ...inv, [k]: e.target.value });

  const setItem = (idx, patch) => setItems(items.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const onCode = (idx, code) => {
    const c = cpt.find((x) => x.code === code);
    setItem(idx, { cpt_code: code, description: c?.description || "", amount: c?.amount || 0 });
  };
  const total = items.reduce((s, i) => s + (Number(i.amount) || 0) * (Number(i.quantity) || 0), 0);

  const resetInvoice = () => { setInv(emptyInvoice); setItems([newItem()]); loadNumber(); };

  const save = async () => {
    const valid = items.filter((i) => i.cpt_code || i.description);
    if (!inv.patient_id && !inv.patient_name) { toast.error(t("patient")); return; }
    if (valid.length === 0) { toast.error(t("addItem")); return; }
    try {
      await api.post("/invoices", { ...inv, items: valid });
      toast.success(t("save") + " ✓");
      resetInvoice(); loadInvoices();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const markPaid = async (id) => {
    try { await api.put(`/invoices/${id}/status`, null, { params: { status: "paid" } }); loadInvoices(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  return (
    <div>
      <div className="no-print">
        <PageHeader title={t("invoices")}
          action={<div className="flex flex-wrap gap-2">
            <Btn variant="outline" onClick={resetInvoice} data-testid="new-invoice-btn"><FilePlus2 className="w-4 h-4" />{t("newInvoice")}</Btn>
            <Btn onClick={save} data-testid="save-invoice-btn"><Save className="w-4 h-4" />{t("saveInvoice")}</Btn>
            <Btn variant="outline" onClick={() => window.print()} data-testid="save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
            <Btn variant="outline" onClick={() => window.print()} data-testid="print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
          </div>} />
      </div>

      {/* Invoice document */}
      <Card className="p-6 sm:p-8" >
        <div id="invoice-print">
          <Letterhead settings={settings} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-4">
            <div>
              <h3 className="font-heading text-xs font-bold uppercase tracking-[0.2em] text-moneygreen-600 border-b border-border pb-2 mb-3">{t("patientInformation")}</h3>
              <div className="space-y-2.5">
                <Row label={t("fullName")}>
                  <select value={inv.patient_id} onChange={onPatient} className={cellCls} data-testid="inv-patient">
                    <option value="">{t("selectPatient")}</option>
                    {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
                  </select>
                </Row>
                <Row label={t("dob")}><input type="date" value={inv.dob || ""} onChange={setF("dob")} className={cellCls} data-testid="inv-dob" /></Row>
                <Row label="SSN"><input value={inv.ssn || ""} onChange={setF("ssn")} className={cellCls} data-testid="inv-ssn" placeholder="XXX-XX-XXXX" /></Row>
                <Row label={t("policyNumber")}><input value={inv.policy_number || ""} onChange={setF("policy_number")} className={cellCls} data-testid="inv-policy" /></Row>
                <Row label={t("gender")}>
                  <select value={inv.gender || ""} onChange={setF("gender")} className={cellCls}>
                    <option value="">—</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
                  </select>
                </Row>
              </div>
            </div>

            <div>
              <h3 className="font-heading text-xs font-bold uppercase tracking-[0.2em] text-moneygreen-600 border-b border-border pb-2 mb-3">{t("invoiceInformation")}</h3>
              <div className="space-y-2.5">
                <Row label={t("invoiceNumber")}><input value={inv.invoice_number} onChange={setF("invoice_number")} className={cellCls} data-testid="inv-number" /></Row>
                <Row label={t("serviceDate")}><input type="date" value={inv.service_date} onChange={setF("service_date")} className={cellCls} data-testid="inv-service-date" /></Row>
                <Row label={t("visitReason")}>
                  <select value={inv.visit_reason || ""} onChange={setF("visit_reason")} className={cellCls} data-testid="inv-reason">
                    <option value="">—</option>
                    {reasons.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </Row>
                <Row label="ICD-10-CM"><input value={inv.icd10 || ""} onChange={setF("icd10")} className={cellCls} data-testid="inv-icd10" placeholder="e.g. F41.1" /></Row>
                <Row label={t("attendingProvider")}>
                  <select value={inv.provider || ""} onChange={setF("provider")} className={cellCls} data-testid="inv-provider">
                    <option value="">—</option>
                    {providers.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
                  </select>
                </Row>
              </div>
            </div>
          </div>

          {/* Line items */}
          <div className="mt-8 overflow-x-auto">
            <table className="w-full text-sm border border-border rounded-lg overflow-hidden">
              <thead>
                <tr className="bg-moneygreen-800 text-tan-100 text-left text-xs uppercase tracking-wider">
                  <th className="px-3 py-2 w-8">#</th>
                  <th className="px-3 py-2 w-40">{t("cptCode")}</th>
                  <th className="px-3 py-2">{t("serviceDescription")}</th>
                  <th className="px-3 py-2 w-20">{t("units")}</th>
                  <th className="px-3 py-2 w-24">{t("minutes")}</th>
                  <th className="px-3 py-2 w-28">{t("unitPrice")}</th>
                  <th className="px-3 py-2 w-28 text-right">{t("fee")}</th>
                  <th className="px-3 py-2 w-8 no-print"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, idx) => (
                  <tr key={it._uid} className="border-t border-border" data-testid={`inv-item-${idx}`}>
                    <td className="px-3 py-2 text-stone-500">{idx + 1}</td>
                    <td className="px-3 py-2">
                      <select value={it.cpt_code} onChange={(e) => onCode(idx, e.target.value)} className={cellCls} data-testid={`inv-item-cpt-${idx}`}>
                        <option value="">{t("selectCpt")}</option>
                        {cpt.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2"><input value={it.description} onChange={(e) => setItem(idx, { description: e.target.value })} className={cellCls} data-testid={`inv-item-desc-${idx}`} /></td>
                    <td className="px-3 py-2"><input type="number" min="0" value={it.quantity} onChange={(e) => { const q = Math.max(0, +e.target.value || 0); setItem(idx, { quantity: q, minutes: q * 15 }); }} className={cellCls} data-testid={`inv-item-units-${idx}`} /></td>
                    <td className="px-3 py-2"><input type="number" value={it.minutes} readOnly tabIndex={-1} className={`${cellCls} bg-tan-50 text-stone-500 cursor-not-allowed`} data-testid={`inv-item-minutes-${idx}`} /></td>
                    <td className="px-3 py-2"><input type="number" min="0" step="0.01" value={it.amount} onChange={(e) => setItem(idx, { amount: +e.target.value || 0 })} className={cellCls} data-testid={`inv-item-price-${idx}`} /></td>
                    <td className="px-3 py-2 text-right font-semibold text-moneygreen-800" data-testid={`inv-item-fee-${idx}`}>${((Number(it.amount) || 0) * (Number(it.quantity) || 0)).toFixed(2)}</td>
                    <td className="px-3 py-2 no-print">
                      {items.length > 1 && <button type="button" onClick={() => setItems(items.filter((_, i) => i !== idx))} className="text-destructive"><Trash2 className="w-4 h-4" /></button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between mt-4">
            <Btn variant="outline" onClick={() => setItems([...items, newItem()])} data-testid="add-service-btn" className="no-print"><Plus className="w-4 h-4" />{t("addService")}</Btn>
            <div className="text-right ml-auto">
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500 mr-4">{t("total")}</span>
              <span className="font-heading text-3xl font-extrabold text-moneygreen-800" data-testid="invoice-total">${total.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Saved invoices */}
      <div className="mt-8 no-print">
        <h3 className="font-heading text-lg font-bold text-moneygreen-800 mb-3">{t("savedInvoices")}</h3>
        <Card className="overflow-hidden">
          {invoices.length === 0 ? <p className="p-6 text-sm text-stone-400">{t("noData")}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
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
                    <tr key={v.id} data-testid={`invoice-row-${v.id}`} className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                      <td className="px-5 py-3 font-mono font-semibold text-moneygreen-700">{v.invoice_number || "—"}</td>
                      <td className="px-5 py-3 text-stone-700">{v.patient_name}</td>
                      <td className="px-5 py-3 hidden md:table-cell text-stone-600">{v.service_date || (v.created_at || "").slice(0, 10)}</td>
                      <td className="px-5 py-3"><Badge tone={v.status === "paid" ? "green" : "amber"}>{t(v.status)}</Badge></td>
                      <td className="px-5 py-3 text-right font-semibold text-moneygreen-800">${(v.total || 0).toFixed(2)}</td>
                      <td className="px-5 py-3 text-right">
                        {v.status !== "paid" && <Btn variant="outline" onClick={() => markPaid(v.id)} data-testid={`mark-paid-${v.id}`}><CheckCircle2 className="w-4 h-4" />{t("markPaid")}</Btn>}
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

const Row = ({ label, children }) => (
  <div className="grid grid-cols-3 items-center gap-2">
    <span className="text-xs font-semibold text-stone-500">{label}</span>
    <div className="col-span-2">{children}</div>
  </div>
);
