import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { Plus, Trash2, CheckCircle2, ReceiptText } from "lucide-react";
import { toast } from "sonner";

let itemSeq = 0;
const newItem = () => ({ _uid: `it-${itemSeq++}`, cpt_code: "", description: "", amount: 0, quantity: 1 });

export default function Invoices() {
  const { t } = useLang();
  const { user } = useAuth();
  const allowed = can(user?.role, "invoices");
  const [invoices, setInvoices] = useState([]);
  const [patients, setPatients] = useState([]);
  const [cpt, setCpt] = useState([]);
  const [open, setOpen] = useState(false);
  const [patientId, setPatientId] = useState("");
  const [items, setItems] = useState([newItem()]);

  const load = () => api.get("/invoices").then((r) => setInvoices(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/cpt-codes").then((r) => setCpt(r.data)).catch(() => {});
  }, []);

  const addItem = () => setItems([...items, newItem()]);
  const setItem = (idx, code) => {
    const c = cpt.find((x) => x.code === code);
    const next = [...items];
    next[idx] = { ...next[idx], cpt_code: code, description: c?.description || "", amount: c?.amount || 0 };
    setItems(next);
  };
  const setQty = (idx, q) => { const next = [...items]; next[idx].quantity = Math.max(1, +q || 1); setItems(next); };
  const removeItem = (idx) => setItems(items.filter((_, i) => i !== idx));
  const total = items.reduce((s, i) => s + i.amount * i.quantity, 0);

  const save = async (e) => {
    e.preventDefault();
    const valid = items.filter((i) => i.cpt_code);
    if (!patientId || valid.length === 0) { toast.error(t("cptCode")); return; }
    try {
      await api.post("/invoices", { patient_id: patientId, items: valid, status: "unpaid" });
      toast.success(t("save") + " ✓");
      setOpen(false); setItems([newItem()]); setPatientId(""); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const markPaid = async (id) => {
    try { await api.put(`/invoices/${id}/status`, null, { params: { status: "paid" } }); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  return (
    <div>
      <PageHeader title={t("invoices")} subtitle={`${invoices.length}`}
        action={allowed && <Btn onClick={() => setOpen(true)} data-testid="add-invoice-btn"><Plus className="w-4 h-4" />{t("newInvoice")}</Btn>} />

      {invoices.length === 0 ? <Card><Empty text={t("noData")} /></Card> : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {invoices.map((inv, i) => (
            <motion.div key={inv.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Card className="p-5" data-testid={`invoice-card-${inv.id}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-md bg-tan-200 flex items-center justify-center">
                      <ReceiptText className="w-4 h-4 text-tan-900" />
                    </div>
                    <div>
                      <p className="font-heading font-bold text-moneygreen-800">{inv.patient_name}</p>
                      <p className="text-xs text-stone-500">{inv.items.length} {t("items").toLowerCase()}</p>
                    </div>
                  </div>
                  <Badge tone={inv.status === "paid" ? "green" : "amber"}>{t(inv.status)}</Badge>
                </div>
                <div className="space-y-1 mb-3">
                  {inv.items.map((it, k) => (
                    <div key={`${it.cpt_code}-${k}`} className="flex justify-between text-sm">
                      <span className="text-stone-600"><span className="font-mono text-moneygreen-600">{it.cpt_code}</span> {it.description} ×{it.quantity}</span>
                      <span className="text-stone-700">${(it.amount * it.quantity).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between pt-3 border-t border-border">
                  <span className="font-heading font-bold text-lg text-moneygreen-800">${inv.total.toFixed(2)}</span>
                  {inv.status !== "paid" && allowed && (
                    <Btn variant="outline" onClick={() => markPaid(inv.id)} data-testid={`mark-paid-${inv.id}`}>
                      <CheckCircle2 className="w-4 h-4" />{t("markPaid")}
                    </Btn>
                  )}
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={t("newInvoice")} wide>
        <form onSubmit={save} className="space-y-4">
          <Field label={t("patient")}>
            <select required value={patientId} onChange={(e) => setPatientId(e.target.value)} className={inputCls} data-testid="if-patient">
              <option value="">—</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </Field>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("items")}</p>
              <Btn type="button" variant="ghost" onClick={addItem} data-testid="add-item-btn"><Plus className="w-4 h-4" />{t("addItem")}</Btn>
            </div>
            {items.map((it, idx) => (
              <div key={it._uid} className="flex gap-2 items-center">
                <select value={it.cpt_code} onChange={(e) => setItem(idx, e.target.value)} className={inputCls + " flex-1"} data-testid={`item-cpt-${idx}`}>
                  <option value="">{t("cptCode")}</option>
                  {cpt.map((c) => <option key={c.code} value={c.code}>{c.code} — {c.description} (${c.amount})</option>)}
                </select>
                <input type="number" min="1" value={it.quantity} onChange={(e) => setQty(idx, e.target.value)} className={inputCls + " w-16"} />
                <span className="w-20 text-right text-sm text-stone-600">${(it.amount * it.quantity).toFixed(2)}</span>
                {items.length > 1 && <button type="button" onClick={() => removeItem(idx)} className="text-destructive"><Trash2 className="w-4 h-4" /></button>}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-border">
            <span className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("total")}</span>
            <span className="font-heading font-extrabold text-2xl text-moneygreen-800" data-testid="invoice-total">${total.toFixed(2)}</span>
          </div>
          <div className="flex justify-end gap-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-invoice-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
