import React, { useEffect, useState } from "react";
import api, { apiErr } from "../lib/api";
import { useSearchParams } from "react-router-dom";
import { useSelection, bulkDelete } from "../lib/bulk";
import { usePrivacy, Private } from "../context/PrivacyContext";
import { useLang } from "../context/LanguageContext";
import { Letterhead } from "../components/Letterhead";
import { PageHeader, Btn, Card, Badge, inputCls, Modal } from "../components/ui-kit";
import { Plus, Trash2, FilePlus2, Save, FileDown, Printer, NotebookPen, ChevronRight, Eye, Pencil } from "lucide-react";
import { toast } from "sonner";

let seq = 0;
const newItem = () => ({ _uid: `it-${seq++}`, cpt_code: "", description: "", quantity: 1, minutes: 15, amount: 0 });
const emptyInvoice = {
  patient_id: "", patient_name: "", dob: "", ssn: "", policy_number: "", gender: "",
  invoice_number: "", service_date: new Date().toISOString().slice(0, 10),
  visit_reason: "", icd10: "", provider: "", status: "in_transit",
};
const reasons = ["General Consultation", "Physical Therapy", "Therapeutic Massage", "Relaxing Massage", "Evaluation", "Follow-up", "Re-evaluation", "Psychotherapy", "Group Therapy"];
const STATUSES = ["in_transit", "paid", "denied"];
const statusTone = { paid: "green", in_transit: "amber", denied: "red", unpaid: "amber", void: "gray", outstanding: "amber" };
const statusKey = { in_transit: "inTransit", paid: "paid", denied: "denied", unpaid: "unpaid", void: "draft", outstanding: "outstanding" };

const cellCls = "w-full px-2 py-1.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm";

export default function Invoices() {
  const { t } = useLang();
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status");
  const sel = useSelection();
  const [settings, setSettings] = useState(null);
  const [patients, setPatients] = useState([]);
  const [cpt, setCpt] = useState([]);
  const [providers, setProviders] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [inv, setInv] = useState(emptyInvoice);
  const [items, setItems] = useState([newItem()]);
  const [editId, setEditId] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [noteModal, setNoteModal] = useState(false);
  const [notePatient, setNotePatient] = useState("");
  const [billingNotes, setBillingNotes] = useState([]);
  const [loadingNotes, setLoadingNotes] = useState(false);

  const statusLabel = (s) => t(statusKey[s] || s);
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

  const shownInvoices = statusFilter
    ? invoices.filter((v) => (statusFilter === "outstanding" ? v.status !== "paid" : v.status === statusFilter))
    : invoices;

  const onPatient = (e) => {
    const p = patients.find((x) => x.id === e.target.value);
    setInv((s) => ({
      ...s, patient_id: e.target.value,
      patient_name: p ? `${p.first_name} ${p.last_name}` : "",
      dob: p?.dob || s.dob, gender: p?.gender || s.gender, ssn: p?.ssn || s.ssn,
    }));
  };
  const setF = (k) => (e) => setInv({ ...inv, [k]: e.target.value });

  const setItem = (idx, patch) => setItems(items.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const onCode = (idx, code) => {
    const c = cpt.find((x) => x.code === code);
    setItem(idx, { cpt_code: code, description: c?.description || "", amount: c?.amount || 0 });
  };
  const total = items.reduce((s, i) => s + (Number(i.amount) || 0) * (Number(i.quantity) || 0), 0);

  const resetInvoice = () => { setEditId(null); setInv(emptyInvoice); setItems([newItem()]); loadNumber(); };

  const openNoteModal = () => { setNotePatient(""); setBillingNotes([]); setNoteModal(true); };
  const onNotePatient = (e) => {
    const pid = e.target.value;
    setNotePatient(pid);
    setBillingNotes([]);
    if (!pid) return;
    setLoadingNotes(true);
    api.get("/notes/for-billing", { params: { patient_id: pid } })
      .then((r) => setBillingNotes(r.data))
      .catch((err) => toast.error(apiErr(err)))
      .finally(() => setLoadingNotes(false));
  };
  const applyNote = (n) => {
    const p = patients.find((x) => x.id === notePatient);
    setInv((s) => ({
      ...s,
      patient_id: notePatient,
      patient_name: p ? `${p.first_name} ${p.last_name}` : s.patient_name,
      dob: n.dob || p?.dob || s.dob,
      gender: n.gender || p?.gender || s.gender,
      ssn: n.ssn || s.ssn,
      service_date: n.visit_date || (n.created_at || "").slice(0, 10) || s.service_date,
      visit_reason: n.reason_for_visit || s.visit_reason,
      icd10: n.icd10 || s.icd10,
      provider: n.attending_provider || s.provider,
    }));
    setNoteModal(false);
    toast.success(t("prefilledFromNote"));
  };
  const reasonOptions = inv.visit_reason && !reasons.includes(inv.visit_reason)
    ? [inv.visit_reason, ...reasons] : reasons;

  const save = async () => {
    const valid = items.filter((i) => i.cpt_code || i.description).map(({ _uid, ...rest }) => rest);
    if (!inv.patient_id && !inv.patient_name) { toast.error(t("patient")); return; }
    if (valid.length === 0) { toast.error(t("addItem")); return; }
    try {
      if (editId) { await api.put(`/invoices/${editId}`, { ...inv, items: valid }); toast.success(t("updated")); }
      else { await api.post("/invoices", { ...inv, items: valid }); toast.success(t("save") + " ✓"); }
      resetInvoice(); loadInvoices();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const editInvoice = async (id) => {
    try {
      const r = await api.get(`/invoices/${id}`);
      const d = r.data;
      setEditId(id);
      setInv({
        patient_id: d.patient_id || "", patient_name: d.patient_name || "", dob: d.dob || "",
        ssn: d.ssn || "", policy_number: d.policy_number || "", gender: d.gender || "",
        invoice_number: d.invoice_number || "", service_date: d.service_date || new Date().toISOString().slice(0, 10),
        visit_reason: d.visit_reason || "", icd10: d.icd10 || "", provider: d.provider || "", status: d.status || "in_transit",
      });
      setItems((d.items || []).length ? d.items.map((it) => ({ _uid: `it-${seq++}`, ...it })) : [newItem()]);
      setViewing(null);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) { toast.error(apiErr(err)); }
  };

  const viewInvoice = async (id) => {
    try { setViewing((await api.get(`/invoices/${id}`)).data); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const changeStatus = async (id, status) => {
    try { await api.put(`/invoices/${id}/status`, null, { params: { status } }); toast.success(t("updated")); loadInvoices(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const removeInvoice = async (id) => {
    try { await api.delete(`/invoices/${id}`); loadInvoices(); } catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    try { await bulkDelete("/invoices/bulk-delete", [...sel.selected], t); sel.clear(); loadInvoices(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  // Only one invoice prints at a time: when a saved invoice is being viewed,
  // the view modal owns the #invoice-print id; otherwise the editor owns it.
  const editorPrintId = viewing ? "editor-doc" : "invoice-print";

  return (
    <div>
      <div className="no-print">
        <PageHeader title={t("invoices")} subtitle={editId ? `${t("editInvoice")} · ${inv.invoice_number}` : ""}
          action={<div className="flex flex-wrap gap-2">
            <Btn variant="outline" onClick={openNoteModal} data-testid="create-from-note-btn"><NotebookPen className="w-4 h-4" />{t("createFromNote")}</Btn>
            <Btn variant="outline" onClick={resetInvoice} data-testid="new-invoice-btn"><FilePlus2 className="w-4 h-4" />{t("newInvoice")}</Btn>
            <Btn onClick={save} data-testid="save-invoice-btn"><Save className="w-4 h-4" />{editId ? t("save") : t("saveInvoice")}</Btn>
            <Btn variant="outline" onClick={() => window.print()} data-testid="save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
            <Btn variant="outline" onClick={() => window.print()} data-testid="print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
          </div>} />
      </div>

      {/* Invoice editor document */}
      <Card className="p-6 sm:p-8">
        <div id={editorPrintId}>
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
                <Row label={t("status")}>
                  <select value={inv.status} onChange={setF("status")} className={cellCls} data-testid="inv-status">
                    {STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                  </select>
                </Row>
                <Row label={t("visitReason")}>
                  <select value={inv.visit_reason || ""} onChange={setF("visit_reason")} className={cellCls} data-testid="inv-reason">
                    <option value="">—</option>
                    {reasonOptions.map((r) => <option key={r} value={r}>{r}</option>)}
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
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h3 className="font-heading text-lg font-bold text-moneygreen-800">{t("savedInvoices")}</h3>
          {statusFilter && (
            <Badge tone={statusTone[statusFilter] || "gray"} className="flex items-center gap-1" data-testid="invoice-status-filter">
              {statusLabel(statusFilter)}
              <button onClick={() => { params.delete("status"); setParams(params); }} data-testid="clear-invoice-filter" className="ml-1 underline">{t("clearFilter")}</button>
            </Badge>
          )}
          {shownInvoices.length > 0 && (
            <div className="ml-auto flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-sm text-stone-600 cursor-pointer">
                <input type="checkbox" data-testid="select-all-invoices"
                  checked={sel.count >= shownInvoices.length && shownInvoices.length > 0}
                  onChange={() => sel.toggleAll(shownInvoices.map((v) => v.id))}
                  className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                {t("selectAll")}
              </label>
              {sel.count > 0 && (<>
                <span className="text-sm text-stone-500">{sel.count}</span>
                <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-invoices"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
                <Btn variant="outline" onClick={sel.clear} data-testid="deselect-invoices">{t("deselectAll")}</Btn>
              </>)}
            </div>
          )}
        </div>
        <Card className="overflow-hidden">
          {shownInvoices.length === 0 ? <p className="p-6 text-sm text-stone-400">{t("noData")}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="px-4 py-3 w-8">
                      <input type="checkbox" data-testid="select-all-invoices-head"
                        checked={sel.count >= shownInvoices.length && shownInvoices.length > 0}
                        onChange={() => sel.toggleAll(shownInvoices.map((v) => v.id))}
                        className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                    </th>
                    <th className="px-5 py-3">{t("invoiceNumber")}</th>
                    <th className="px-5 py-3">{t("patient")}</th>
                    <th className="px-5 py-3 hidden md:table-cell">{t("serviceDate")}</th>
                    <th className="px-5 py-3">{t("status")}</th>
                    <th className="px-5 py-3 text-right">{t("total")}</th>
                    <th className="px-5 py-3 text-right">{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {shownInvoices.map((v, i) => (
                    <tr key={v.id} data-testid={`invoice-row-${v.id}`} className={`border-b border-border/60 ${sel.has(v.id) ? "bg-moneygreen-50" : i % 2 ? "bg-tan-50/40" : ""}`}>
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={sel.has(v.id)} onChange={() => sel.toggle(v.id)}
                          data-testid={`select-invoice-${v.id}`} className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                      </td>
                      <td className="px-5 py-3 font-mono font-semibold text-moneygreen-700">{v.invoice_number || "—"}</td>
                      <td className="px-5 py-3 text-stone-700"><Private value={v.patient_name} /></td>
                      <td className="px-5 py-3 hidden md:table-cell text-stone-600">{v.service_date || (v.created_at || "").slice(0, 10)}</td>
                      <td className="px-5 py-3">
                        <select value={STATUSES.includes(v.status) ? v.status : "in_transit"} onChange={(e) => changeStatus(v.id, e.target.value)}
                          data-testid={`invoice-status-${v.id}`} title={t("changeStatus")}
                          className={`px-2 py-1 rounded-md border text-xs font-semibold cursor-pointer focus:outline-none focus:ring-2 focus:ring-moneygreen-500 ${statusTone[v.status] === "green" ? "bg-moneygreen-100 text-moneygreen-700 border-moneygreen-200" : statusTone[v.status] === "red" ? "bg-red-100 text-red-700 border-red-200" : "bg-amber-100 text-amber-700 border-amber-200"}`}>
                          {STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                        </select>
                      </td>
                      <td className="px-5 py-3 text-right font-semibold text-moneygreen-800">${(v.total || 0).toFixed(2)}</td>
                      <td className="px-5 py-3 text-right">
                        <div className="flex justify-end gap-1">
                          <Btn variant="ghost" onClick={() => viewInvoice(v.id)} data-testid={`view-invoice-${v.id}`} className="!px-2" title={t("view")}><Eye className="w-4 h-4" /></Btn>
                          <Btn variant="ghost" onClick={() => editInvoice(v.id)} data-testid={`edit-invoice-${v.id}`} className="!px-2" title={t("edit")}><Pencil className="w-4 h-4" /></Btn>
                          <Btn variant="ghost" onClick={() => removeInvoice(v.id)} data-testid={`delete-invoice-${v.id}`} className="!px-2 !text-destructive" title={t("delete")}><Trash2 className="w-4 h-4" /></Btn>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* View single invoice */}
      <Modal open={!!viewing} onClose={() => setViewing(null)} title={viewing ? `${t("invoiceNumber")} ${viewing.invoice_number || ""}` : ""} wide>
        {viewing && (
          <div className="space-y-4">
            <div id="invoice-print" data-testid="invoice-view">
              <Letterhead settings={settings} />
              <div className="flex items-center justify-between mt-3">
                <div>
                  <p className="font-mono font-bold text-moneygreen-700">{viewing.invoice_number}</p>
                  <p className="text-sm text-stone-500">{viewing.service_date || (viewing.created_at || "").slice(0, 10)}</p>
                </div>
                <Badge tone={statusTone[viewing.status] || "gray"}>{statusLabel(viewing.status)}</Badge>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5 text-sm mt-4">
                <div><span className="text-xs font-semibold text-stone-500">{t("fullName")}: </span><Private value={viewing.patient_name} /></div>
                {viewing.dob && <div><span className="text-xs font-semibold text-stone-500">{t("dob")}: </span><Private value={viewing.dob} /></div>}
                {viewing.ssn && <div><span className="text-xs font-semibold text-stone-500">SSN: </span><Private value={viewing.ssn} /></div>}
                {viewing.gender && <div><span className="text-xs font-semibold text-stone-500">{t("gender")}: </span>{viewing.gender}</div>}
                {viewing.visit_reason && <div><span className="text-xs font-semibold text-stone-500">{t("visitReason")}: </span>{viewing.visit_reason}</div>}
                {viewing.icd10 && <div><span className="text-xs font-semibold text-stone-500">ICD-10-CM: </span>{viewing.icd10}</div>}
                {viewing.provider && <div><span className="text-xs font-semibold text-stone-500">{t("attendingProvider")}: </span>{viewing.provider}</div>}
              </div>
              <div className="mt-5 overflow-x-auto">
                <table className="w-full text-sm border border-border rounded-lg overflow-hidden">
                  <thead>
                    <tr className="bg-moneygreen-800 text-tan-100 text-left text-xs uppercase tracking-wider">
                      <th className="px-3 py-2">{t("cptCode")}</th>
                      <th className="px-3 py-2">{t("serviceDescription")}</th>
                      <th className="px-3 py-2 w-20">{t("units")}</th>
                      <th className="px-3 py-2 w-24">{t("minutes")}</th>
                      <th className="px-3 py-2 w-28">{t("unitPrice")}</th>
                      <th className="px-3 py-2 w-28 text-right">{t("fee")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(viewing.items || []).map((it, idx) => (
                      <tr key={idx} className="border-t border-border">
                        <td className="px-3 py-2 font-mono">{it.cpt_code || "—"}</td>
                        <td className="px-3 py-2">{it.description}</td>
                        <td className="px-3 py-2">{it.quantity}</td>
                        <td className="px-3 py-2">{it.minutes}</td>
                        <td className="px-3 py-2">${(Number(it.amount) || 0).toFixed(2)}</td>
                        <td className="px-3 py-2 text-right font-semibold text-moneygreen-800">${((Number(it.amount) || 0) * (Number(it.quantity) || 0)).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="text-right mt-4">
                <span className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500 mr-4">{t("total")}</span>
                <span className="font-heading text-3xl font-extrabold text-moneygreen-800">${(viewing.total || 0).toFixed(2)}</span>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 no-print">
              <Btn variant="outline" onClick={() => editInvoice(viewing.id)} data-testid="view-edit-invoice-btn"><Pencil className="w-4 h-4" />{t("edit")}</Btn>
              <Btn variant="outline" onClick={() => window.print()} data-testid="view-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
              <Btn variant="outline" onClick={() => window.print()} data-testid="view-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={noteModal} onClose={() => setNoteModal(false)} title={t("createFromNote")} wide>
        <div className="space-y-4">
          <p className="text-sm text-stone-500">{t("selectNoteHint")}</p>
          <div>
            <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("patient")}</label>
            <select value={notePatient} onChange={onNotePatient} className={`${inputCls} mt-1.5`} data-testid="note-patient-select">
              <option value="">{t("selectPatient")}</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </div>
          {notePatient && (
            <div className="space-y-2 max-h-[45vh] overflow-y-auto custom-scroll" data-testid="billing-notes-list">
              {loadingNotes ? <p className="text-sm text-stone-400 py-6 text-center">…</p>
                : billingNotes.length === 0 ? <p className="text-sm text-stone-400 py-6 text-center">{t("noNotesForPatient")}</p>
                : billingNotes.map((n) => (
                  <button key={n.id} type="button" onClick={() => applyNote(n)} data-testid={`billing-note-${n.id}`}
                    className="w-full text-left p-3 rounded-md border border-border hover:border-moneygreen-500 hover:bg-moneygreen-50 transition-colors duration-200 group">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Badge tone="green">{t("session")}</Badge>
                        <span className="text-xs font-mono text-stone-500">{n.visit_date || (n.created_at || "").slice(0, 10)}</span>
                        {n.icd10 && <span className="text-xs text-stone-500">· ICD-10 {n.icd10}</span>}
                      </div>
                      <ChevronRight className="w-4 h-4 text-stone-300 group-hover:text-moneygreen-600 shrink-0" />
                    </div>
                    {n.reason_for_visit && <p className="text-sm font-semibold text-moneygreen-800 mt-1">{n.reason_for_visit}</p>}
                    {n.preview && <p className="text-xs text-stone-500 mt-0.5 line-clamp-2">{n.preview}</p>}
                    {n.attending_provider && <p className="text-xs text-stone-400 mt-1">{t("attendingProvider")}: {n.attending_provider}</p>}
                  </button>
                ))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}

const Row = ({ label, children }) => (
  <div className="grid grid-cols-3 items-center gap-2">
    <span className="text-xs font-semibold text-stone-500">{label}</span>
    <div className="col-span-2">{children}</div>
  </div>
);
