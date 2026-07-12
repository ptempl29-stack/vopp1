import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { Plus, ClipboardList, CheckCircle2, Link2, Eye } from "lucide-react";
import { toast } from "sonner";

const types = ["Intake", "Consent", "Medical History", "Insurance", "Referral"];
const toneMap = { sent: "amber", pending: "amber", received: "green" };

export default function Forms() {
  const { t } = useLang();
  const [forms, setForms] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [form, setForm] = useState({ patient_id: "", title: "", form_type: "Intake", status: "sent" });

  const load = () => api.get("/forms").then((r) => setForms(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/patients").then((r) => setPatients(r.data)).catch(() => {}); }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const copyLink = (f) => {
    const url = `${window.location.origin}/form/${f.public_token}`;
    navigator.clipboard.writeText(url).then(() => toast.success(t("linkCopied")))
      .catch(() => toast.error(url));
  };

  const save = async (e) => {
    e.preventDefault();
    try { await api.post("/forms", form); toast.success(t("save") + " ✓"); setOpen(false); setForm({ patient_id: "", title: "", form_type: "Intake", status: "sent" }); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const markReceived = async (id) => {
    try { await api.put(`/forms/${id}/status`, null, { params: { status: "received" } }); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  return (
    <div>
      <PageHeader title={t("forms")} subtitle={`${forms.length}`}
        action={<Btn onClick={() => setOpen(true)} data-testid="add-form-btn"><Plus className="w-4 h-4" />{t("newForm")}</Btn>} />

      <Card className="overflow-hidden">
        {forms.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("title")}</th>
                  <th className="px-5 py-3">{t("formType")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("patient")}</th>
                  <th className="px-5 py-3">{t("status")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {forms.map((f, i) => (
                  <motion.tr key={f.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`form-row-${f.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2.5">
                        <ClipboardList className="w-4 h-4 text-moneygreen-500" />
                        <span className="font-semibold text-moneygreen-800">{f.title}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-stone-600">{f.form_type}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{f.patient_name}</td>
                    <td className="px-5 py-3"><Badge tone={toneMap[f.status] || "gray"}>{t(f.status)}</Badge></td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Btn variant="ghost" onClick={() => copyLink(f)} data-testid={`copy-link-${f.id}`} className="!px-2" title={t("copyLink")}>
                          <Link2 className="w-4 h-4" />
                        </Btn>
                        {f.status === "received" && f.responses && (
                          <Btn variant="ghost" onClick={() => setViewing(f)} data-testid={`view-responses-${f.id}`} className="!px-2" title={t("viewResponses")}>
                            <Eye className="w-4 h-4" />
                          </Btn>
                        )}
                        {f.status !== "received" && (
                          <Btn variant="outline" onClick={() => markReceived(f.id)} data-testid={`mark-received-${f.id}`}>
                            <CheckCircle2 className="w-4 h-4" />{t("markReceived")}
                          </Btn>
                        )}
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title={t("newForm")}>
        <form onSubmit={save} className="space-y-4">
          <Field label={t("title")}><input required value={form.title} onChange={set("title")} className={inputCls} data-testid="ff-title" /></Field>
          <Field label={t("formType")}>
            <select value={form.form_type} onChange={set("form_type")} className={inputCls} data-testid="ff-type">
              {types.map((ty) => <option key={ty} value={ty}>{ty}</option>)}
            </select>
          </Field>
          <Field label={t("patient")}>
            <select value={form.patient_id} onChange={set("patient_id")} className={inputCls}>
              <option value="">—</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </Field>
          <Field label={t("status")}>
            <select value={form.status} onChange={set("status")} className={inputCls}>
              <option value="sent">{t("sent")}</option><option value="pending">{t("pending")}</option><option value="received">{t("received")}</option>
            </select>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-form-btn">{t("sendForm")}</Btn>
          </div>
        </form>
      </Modal>

      <Modal open={!!viewing} onClose={() => setViewing(null)} title={t("responses")}>
        {viewing && (
          <div className="space-y-3" data-testid="responses-view">
            <p className="font-heading font-bold text-moneygreen-800">{viewing.title}</p>
            {viewing.responses && Object.keys(viewing.responses).length > 0 ? (
              (viewing.template || []).filter((fld) => viewing.responses[fld.name] !== undefined && viewing.responses[fld.name] !== "").map((fld) => (
                <div key={fld.name} className="border-b border-border pb-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{fld.en}</p>
                  <p className="text-sm text-moneygreen-800 mt-0.5">{String(viewing.responses[fld.name])}</p>
                </div>
              ))
            ) : <p className="text-sm text-stone-500">{t("noResponses")}</p>}
          </div>
        )}
      </Modal>
    </div>
  );
}
