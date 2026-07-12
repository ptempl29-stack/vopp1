import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Empty, Card } from "../components/ui-kit";
import { SignaturePad } from "../components/SignaturePad";
import { Plus, Sparkles, Loader2, FileText, PenLine } from "lucide-react";
import { toast } from "sonner";

const blank = { patient_id: "", title: "", content: "", note_type: "free",
  subjective: "", objective: "", assessment: "", plan: "", summary: "", signature: "" };

const soapText = (f) => [["S", f.subjective], ["O", f.objective], ["A", f.assessment], ["P", f.plan]]
  .filter(([, v]) => v && v.trim()).map(([k, v]) => `${k}: ${v}`).join("\n");

export default function Notes() {
  const { t } = useLang();
  const { user } = useAuth();
  const allowed = can(user?.role, "notes");
  const [notes, setNotes] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [summarizing, setSummarizing] = useState(false);

  const load = () => api.get("/notes").then((r) => setNotes(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/patients").then((r) => setPatients(r.data)).catch(() => {}); }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const noteText = () => (form.note_type === "soap" ? soapText(form) : form.content);

  const summarize = async () => {
    const text = noteText();
    if (!text.trim()) { toast.error(t("content")); return; }
    setSummarizing(true);
    try {
      const r = await api.post("/notes/summarize", { content: text });
      setForm((f) => ({ ...f, summary: r.data.summary }));
      toast.success(t("aiSummary") + " ✓");
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSummarizing(false); }
  };

  const save = async (e) => {
    e.preventDefault();
    if (form.note_type === "soap" && !soapText(form).trim()) { toast.error(t("content")); return; }
    try { await api.post("/notes", form); toast.success(t("save") + " ✓"); setOpen(false); setForm(blank); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const patientName = (id) => {
    const p = patients.find((x) => x.id === id);
    return p ? `${p.first_name} ${p.last_name}` : "—";
  };

  return (
    <div>
      <PageHeader title={t("notes")} subtitle={`${notes.length}`}
        action={allowed && <Btn onClick={() => { setForm(blank); setOpen(true); }} data-testid="add-note-btn"><Plus className="w-4 h-4" />{t("newNote")}</Btn>} />

      {notes.length === 0 ? <Card><Empty text={t("noData")} /></Card> : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {notes.map((n, i) => (
            <motion.div key={n.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Card className="p-5" data-testid={`note-card-${n.id}`}>
                <div className="flex items-start gap-3 mb-2">
                  <div className="w-9 h-9 rounded-md bg-moneygreen-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-moneygreen-600" />
                  </div>
                  <div>
                    <p className="font-heading font-bold text-moneygreen-800">{n.title}</p>
                    <p className="text-xs text-stone-500">{patientName(n.patient_id)} · {n.author}</p>
                  </div>
                  {n.note_type === "soap" && (
                    <span className="ml-auto px-2 py-0.5 rounded-full text-xs font-semibold bg-tan-200 text-tan-900">SOAP</span>
                  )}
                </div>
                {n.note_type === "soap" ? (
                  <div className="space-y-1.5" data-testid={`soap-view-${n.id}`}>
                    {[["S", n.subjective, t("soapS")], ["O", n.objective, t("soapO")], ["A", n.assessment, t("soapA")], ["P", n.plan, t("soapP")]]
                      .filter(([, v]) => v).map(([k, v, label]) => (
                        <div key={k} className="text-sm">
                          <span className="font-bold text-moneygreen-700">{label}: </span>
                          <span className="text-stone-600">{v}</span>
                        </div>
                      ))}
                  </div>
                ) : (
                  <p className="text-sm text-stone-600 whitespace-pre-wrap line-clamp-4">{n.content}</p>
                )}
                {n.summary && (
                  <div className="mt-3 p-3 rounded-md bg-moneygreen-50 border border-moneygreen-100">
                    <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5 mb-1">
                      <Sparkles className="w-3.5 h-3.5" /> {t("aiSummary")}
                    </p>
                    <p className="text-sm text-moneygreen-800">{n.summary}</p>
                  </div>
                )}
                {n.signature && (
                  <div className="mt-3 pt-3 border-t border-border flex items-end justify-between">
                    <img src={n.signature} alt="signature" className="h-12 object-contain" data-testid={`note-sig-${n.id}`} />
                    <p className="text-xs text-stone-500 text-right">{t("signedBy")}<br /><span className="font-semibold text-moneygreen-700">{n.signed_by}</span></p>
                  </div>
                )}
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={t("newNote")} wide>
        <form onSubmit={save} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("patient")}>
              <select required value={form.patient_id} onChange={set("patient_id")} className={inputCls} data-testid="nf-patient">
                <option value="">—</option>
                {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
              </select>
            </Field>
            <Field label={t("title")}><input required value={form.title} onChange={set("title")} className={inputCls} data-testid="nf-title" /></Field>
          </div>

          <Field label={t("noteType")}>
            <div className="flex gap-2">
              <button type="button" onClick={() => setForm({ ...form, note_type: "free" })} data-testid="note-type-free"
                className={`flex-1 py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.note_type === "free" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                {t("freeText")}
              </button>
              <button type="button" onClick={() => setForm({ ...form, note_type: "soap" })} data-testid="note-type-soap"
                className={`flex-1 py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.note_type === "soap" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                {t("soapNote")}
              </button>
            </div>
          </Field>

          {form.note_type === "free" ? (
            <Field label={t("content")}>
              <textarea value={form.content} onChange={set("content")} rows={6} className={inputCls} data-testid="nf-content"
                placeholder="Progress note..." />
            </Field>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="soap-fields">
              <Field label={t("soapS")}><textarea value={form.subjective} onChange={set("subjective")} rows={4} className={inputCls} data-testid="nf-subjective" placeholder={t("soapSHint")} /></Field>
              <Field label={t("soapO")}><textarea value={form.objective} onChange={set("objective")} rows={4} className={inputCls} data-testid="nf-objective" placeholder={t("soapOHint")} /></Field>
              <Field label={t("soapA")}><textarea value={form.assessment} onChange={set("assessment")} rows={4} className={inputCls} data-testid="nf-assessment" placeholder={t("soapAHint")} /></Field>
              <Field label={t("soapP")}><textarea value={form.plan} onChange={set("plan")} rows={4} className={inputCls} data-testid="nf-plan" placeholder={t("soapPHint")} /></Field>
            </div>
          )}

          <div className="p-4 rounded-md bg-moneygreen-50 border border-moneygreen-100">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" /> {t("aiSummary")}
              </p>
              <Btn type="button" variant="outline" onClick={summarize} disabled={summarizing} data-testid="ai-summarize-btn">
                {summarizing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                {summarizing ? t("summarizing") : t("aiSummarize")}
              </Btn>
            </div>
            <textarea value={form.summary} onChange={set("summary")} rows={3} className={inputCls}
              data-testid="nf-summary" placeholder={t("aiSummary")} />
          </div>

          <div className="p-4 rounded-md bg-tan-50 border border-tan-200">
            <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5 mb-2">
              <PenLine className="w-3.5 h-3.5" /> {t("providerSignature")}
            </p>
            <SignaturePad value={form.signature} onChange={(v) => setForm((f) => ({ ...f, signature: v }))} testid="note-signature" />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-note-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
