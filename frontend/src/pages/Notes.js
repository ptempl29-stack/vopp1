import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Empty, Card } from "../components/ui-kit";
import { SignaturePad } from "../components/SignaturePad";
import { Letterhead, EditableLetterhead } from "../components/Letterhead";
import { Plus, Sparkles, Loader2, FileText, PenLine, Printer, FileDown, Stethoscope } from "lucide-react";
import { toast } from "sonner";

const reasons = ["General Consultation", "Physical Therapy", "Therapeutic Massage", "Relaxing Massage", "Evaluation", "Follow-up", "Re-evaluation", "Psychotherapy", "Group Therapy"];

const blank = { patient_id: "", title: "", content: "", note_type: "free",
  subjective: "", objective: "", assessment: "", plan: "", summary: "", signature: "",
  dob: "", gender: "", ssn: "", visit_date: new Date().toISOString().slice(0, 10),
  reason_for_visit: "", attending_provider: "", referring_provider: "", icd10: "" };

const soapText = (f) => [["S", f.subjective], ["O", f.objective], ["A", f.assessment], ["P", f.plan]]
  .filter(([, v]) => v && v.trim()).map(([k, v]) => `${k}: ${v}`).join("\n");

export default function Notes() {
  const { t } = useLang();
  const { user } = useAuth();
  const allowed = can(user?.role, "notes");
  const [notes, setNotes] = useState([]);
  const [patients, setPatients] = useState([]);
  const [providers, setProviders] = useState([]);
  const [settings, setSettings] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [summarizing, setSummarizing] = useState(false);

  const load = () => api.get("/notes").then((r) => setNotes(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
    api.get("/users").then((r) => setProviders(r.data.filter((u) => ["doctor", "nurse", "psychologist"].includes(u.role)))).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onPatient = (e) => {
    const p = patients.find((x) => x.id === e.target.value);
    setForm((f) => ({ ...f, patient_id: e.target.value,
      dob: p?.dob || f.dob, gender: p?.gender || f.gender }));
  };

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
    if (form.note_type === "daily" && !form.content.trim()) { toast.error(t("content")); return; }
    const payload = { ...form };
    if (form.note_type === "daily") {
      payload.title = `${t("dailyNote")} — ${patientName(form.patient_id)}${form.visit_date ? ` · ${form.visit_date}` : ""}`;
    }
    try { await api.post("/notes", payload); toast.success(t("save") + " ✓"); setOpen(false); setForm(blank); load(); }
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
                  {n.note_type === "daily" && (
                    <span className="ml-auto px-2 py-0.5 rounded-full text-xs font-semibold bg-moneygreen-100 text-moneygreen-700 flex items-center gap-1"><Stethoscope className="w-3 h-3" />{t("dailyNote")}</span>
                  )}
                </div>
                {n.note_type === "daily" && (
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500 mb-2" data-testid={`daily-meta-${n.id}`}>
                    {n.visit_date && <span><b className="text-stone-600">{t("visitDate")}:</b> {n.visit_date}</span>}
                    {n.reason_for_visit && <span><b className="text-stone-600">{t("reasonForVisit")}:</b> {n.reason_for_visit}</span>}
                    {n.attending_provider && <span><b className="text-stone-600">{t("attendingProvider")}:</b> {n.attending_provider}</span>}
                    {n.icd10 && <span><b className="text-stone-600">ICD-10:</b> {n.icd10}</span>}
                  </div>
                )}
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
          {form.note_type !== "daily" && (
            <div className="grid grid-cols-2 gap-4">
              <Field label={t("patient")}>
                <select required value={form.patient_id} onChange={onPatient} className={inputCls} data-testid="nf-patient">
                  <option value="">—</option>
                  {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
                </select>
              </Field>
              <Field label={t("title")}><input required value={form.title} onChange={set("title")} className={inputCls} data-testid="nf-title" /></Field>
            </div>
          )}

          <Field label={t("noteType")}>
            <div className="grid grid-cols-3 gap-2">
              <button type="button" onClick={() => setForm({ ...form, note_type: "free" })} data-testid="note-type-free"
                className={`py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.note_type === "free" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                {t("freeText")}
              </button>
              <button type="button" onClick={() => setForm({ ...form, note_type: "soap" })} data-testid="note-type-soap"
                className={`py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.note_type === "soap" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                {t("soapNote")}
              </button>
              <button type="button" onClick={() => setForm({ ...form, note_type: "daily" })} data-testid="note-type-daily"
                className={`py-2 rounded-md text-sm font-semibold border transition-colors duration-200 ${form.note_type === "daily" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-border hover:bg-moneygreen-50"}`}>
                {t("dailyNote")}
              </button>
            </div>
          </Field>

          {form.note_type === "free" && (
            <Field label={t("content")}>
              <textarea value={form.content} onChange={set("content")} rows={6} className={inputCls} data-testid="nf-content"
                placeholder="Progress note..." />
            </Field>
          )}
          {form.note_type === "soap" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="soap-fields">
              <Field label={t("soapS")}><textarea value={form.subjective} onChange={set("subjective")} rows={4} className={inputCls} data-testid="nf-subjective" placeholder={t("soapSHint")} /></Field>
              <Field label={t("soapO")}><textarea value={form.objective} onChange={set("objective")} rows={4} className={inputCls} data-testid="nf-objective" placeholder={t("soapOHint")} /></Field>
              <Field label={t("soapA")}><textarea value={form.assessment} onChange={set("assessment")} rows={4} className={inputCls} data-testid="nf-assessment" placeholder={t("soapAHint")} /></Field>
              <Field label={t("soapP")}><textarea value={form.plan} onChange={set("plan")} rows={4} className={inputCls} data-testid="nf-plan" placeholder={t("soapPHint")} /></Field>
            </div>
          )}
          {form.note_type === "daily" && (
            <div id="note-print" data-testid="daily-fields">
              <div className="rounded-lg border border-border p-4 mb-4">
                <EditableLetterhead settings={settings} onSaved={setSettings} t={t}
                  canEdit={["admin", "doctor", "nurse", "psychologist"].includes(user?.role)} />
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
                <Field label={t("patient")}>
                  <select required value={form.patient_id} onChange={onPatient} className={inputCls} data-testid="nf-patient">
                    <option value="">{t("selectPatient")}</option>
                    {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
                  </select>
                </Field>
                <Field label={t("dob")}><input type="date" value={form.dob || ""} onChange={set("dob")} className={inputCls} data-testid="nf-dob" /></Field>
                <Field label={t("gender")}>
                  <select value={form.gender || ""} onChange={set("gender")} className={inputCls} data-testid="nf-gender">
                    <option value="">—</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
                  </select>
                </Field>
                <Field label="SSN"><input value={form.ssn || ""} onChange={set("ssn")} className={inputCls} data-testid="nf-ssn" placeholder="XXX-XX-XXXX" /></Field>
                <Field label={t("visitDate")}><input type="date" value={form.visit_date || ""} onChange={set("visit_date")} className={inputCls} data-testid="nf-visit-date" /></Field>
                <Field label="ICD-10-CM"><input value={form.icd10 || ""} onChange={set("icd10")} className={inputCls} data-testid="nf-icd10" placeholder="e.g. F33.0" /></Field>
                <Field label={t("reasonForVisit")}>
                  <select value={form.reason_for_visit || ""} onChange={set("reason_for_visit")} className={inputCls} data-testid="nf-reason">
                    <option value="">—</option>
                    {reasons.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </Field>
                <Field label={t("attendingProvider")}>
                  <select value={form.attending_provider || ""} onChange={set("attending_provider")} className={inputCls} data-testid="nf-attending">
                    <option value="">{t("selectProvider")}</option>
                    {providers.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
                  </select>
                </Field>
                <Field label={t("referringProvider")}>
                  <select value={form.referring_provider || ""} onChange={set("referring_provider")} className={inputCls} data-testid="nf-referring">
                    <option value="">{t("selectReferring")}</option>
                    {providers.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
                  </select>
                </Field>
              </div>
              <Field label={t("notesLabel")}>
                <textarea value={form.content} onChange={set("content")} rows={8} className={inputCls} data-testid="nf-daily-content" placeholder="Daily progress note..." />
              </Field>
              {form.summary && (
                <div className="mt-3 p-3 rounded-md bg-moneygreen-50 border border-moneygreen-100">
                  <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5 mb-1"><Sparkles className="w-3.5 h-3.5" /> {t("aiSummary")}</p>
                  <p className="text-sm text-moneygreen-800 whitespace-pre-wrap">{form.summary}</p>
                </div>
              )}
              {form.signature && (
                <div className="mt-3 pt-3 border-t border-border">
                  <p className="text-xs font-bold uppercase tracking-wider text-stone-500 mb-1">{t("providerSignature")}</p>
                  <img src={form.signature} alt="signature" className="h-14 object-contain" />
                </div>
              )}
            </div>
          )}

          {form.note_type === "daily" && (
            <div className="flex justify-end gap-2 no-print">
              <Btn variant="outline" type="button" onClick={() => window.print()} data-testid="note-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
              <Btn variant="outline" type="button" onClick={() => window.print()} data-testid="note-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
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
