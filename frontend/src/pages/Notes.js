import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Empty, Card } from "../components/ui-kit";
import { Plus, Sparkles, Loader2, FileText } from "lucide-react";
import { toast } from "sonner";

const blank = { patient_id: "", title: "", content: "", summary: "" };

export default function Notes() {
  const { t } = useLang();
  const [notes, setNotes] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [summarizing, setSummarizing] = useState(false);

  const load = () => api.get("/notes").then((r) => setNotes(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/patients").then((r) => setPatients(r.data)).catch(() => {}); }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const summarize = async () => {
    if (!form.content.trim()) { toast.error(t("content")); return; }
    setSummarizing(true);
    try {
      const r = await api.post("/notes/summarize", { content: form.content });
      setForm((f) => ({ ...f, summary: r.data.summary }));
      toast.success(t("aiSummary") + " ✓");
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSummarizing(false); }
  };

  const save = async (e) => {
    e.preventDefault();
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
        action={<Btn onClick={() => { setForm(blank); setOpen(true); }} data-testid="add-note-btn"><Plus className="w-4 h-4" />{t("newNote")}</Btn>} />

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
                </div>
                <p className="text-sm text-stone-600 whitespace-pre-wrap line-clamp-4">{n.content}</p>
                {n.summary && (
                  <div className="mt-3 p-3 rounded-md bg-moneygreen-50 border border-moneygreen-100">
                    <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5 mb-1">
                      <Sparkles className="w-3.5 h-3.5" /> {t("aiSummary")}
                    </p>
                    <p className="text-sm text-moneygreen-800">{n.summary}</p>
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
          <Field label={t("content")}>
            <textarea required value={form.content} onChange={set("content")} rows={6} className={inputCls} data-testid="nf-content"
              placeholder="Subjective, objective, assessment..." />
          </Field>

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

          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-note-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  );
}
