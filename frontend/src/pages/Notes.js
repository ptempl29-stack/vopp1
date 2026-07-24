import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useAuth } from "../context/AuthContext";
import { usePrivacy, Private } from "../context/PrivacyContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Btn, Empty, Card, inputCls } from "../components/ui-kit";
import { SignaturePad } from "../components/SignaturePad";
import { Letterhead, EditableLetterhead } from "../components/Letterhead";
import { printSection } from "../lib/print";
import { fmtDate } from "../lib/date";
import { Plus, Sparkles, Loader2, FileText, PenLine, Printer, FileDown, Eye, Pencil, Stamp, Save, Trash2, LayoutGrid, List, Copy, Filter, X } from "lucide-react";
import { toast } from "sonner";

const RISK_LEVELS = ["Low", "Moderate", "High", "Imminent"];
const riskKey = { Low: "riskLow", Moderate: "riskModerate", High: "riskHigh", Imminent: "riskImminent" };

const blank = {
  patient_id: "", title: "", content: "", note_type: "free",
  dob: "", gender: "", ssn: "", visit_date: new Date().toISOString().slice(0, 10),
  icd10: "", cpt_code: "", risk_level: "", attending_provider: "", exequatur_number: "", signature: "",
  summary: "", ai_summarized: false,
};

const headerInputCls = "w-full px-2 py-1 rounded bg-transparent border border-transparent hover:border-border focus:border-moneygreen-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-moneygreen-500 text-sm text-moneygreen-800 font-medium";

export default function Notes() {
  const { t } = useLang();
  const { user, refreshUser } = useAuth();
  const allowed = can(user?.role, "notes");
  const sel = useSelection();
  const [notes, setNotes] = useState([]);
  const [patients, setPatients] = useState([]);
  const [providers, setProviders] = useState([]);
  const [cpt, setCpt] = useState([]);
  const [settings, setSettings] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [summarizing, setSummarizing] = useState(false);
  const [sigKey, setSigKey] = useState(0);
  const [savingSig, setSavingSig] = useState(false);
  const [codeHistory, setCodeHistory] = useState({ icd10: [], cpt: [] });
  const [viewMode, setViewMode] = useState("cards");
  const [providerFilter, setProviderFilter] = useState("");
  const [patientFilter, setPatientFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");

  const load = () => api.get("/notes").then((r) => setNotes(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
    api.get("/cpt-codes").then((r) => setCpt(r.data)).catch(() => {});
    api.get("/users").then((r) => setProviders(r.data.filter((u) => ["doctor", "nurse", "psychologist", "admin"].includes(u.role)))).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const patientName = (id) => {
    const p = patients.find((x) => x.id === id);
    return p ? `${p.first_name} ${p.last_name}` : "—";
  };
  const providerName = (n) => n.attending_provider || n.author || "—";
  const riskLabel = (r) => (r ? t(riskKey[r] || r) : "—");
  const curPatient = (id) => patients.find((x) => x.id === id) || {};

  const noteProvider = (n) => n.attending_provider || n.author || "";
  const noteDate = (n) => n.visit_date || (n.created_at || "").slice(0, 10);
  const providerOptions = useMemo(
    () => [...new Set([...providers.map((u) => u.name), ...notes.map(noteProvider)].filter(Boolean))], [providers, notes]);
  const filtered = useMemo(() => notes.filter((n) =>
    (!providerFilter || noteProvider(n) === providerFilter) &&
    (!patientFilter || n.patient_id === patientFilter) &&
    (!dateFilter || noteDate(n) === dateFilter)
  ), [notes, providerFilter, patientFilter, dateFilter]);

  const onPatient = async (e) => {
    const pid = e.target.value;
    let p = patients.find((x) => x.id === pid);
    try { if (pid) p = (await api.get(`/patients/${pid}`)).data; } catch { /* fallback */ }
    setForm((f) => ({ ...f, patient_id: pid,
      dob: p?.dob || "", gender: p?.gender || "", ssn: p?.ssn || "" }));
    setCodeHistory({ icd10: [], cpt: [] });
    if (pid) api.get("/notes/patient-code-history", { params: { patient_id: pid } })
      .then((r) => setCodeHistory(r.data)).catch(() => {});
  };

  const summarize = async () => {
    const text = (form.content || "").trim();
    if (!text) { toast.error(t("content")); return; }
    setSummarizing(true);
    try {
      const r = await api.post("/notes/summarize", { content: text });
      const s = (r.data.summary || "").trim();
      setForm((f) => ({ ...f, content: f.content.trim() ? `${f.content.trim()} ${s}` : s, summary: "", ai_summarized: true }));
      toast.success(t("aiSummary") + " ✓");
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSummarizing(false); }
  };

  const save = async (e) => {
    e.preventDefault();
    if (!form.patient_id) { toast.error(t("selectPatient")); return; }
    if (!form.content.trim()) { toast.error(t("content")); return; }
    const payload = { ...form, note_type: "free" };
    payload.title = `${t("notes")} — ${patientName(form.patient_id)}${form.visit_date ? ` · ${form.visit_date}` : ""}`;
    try {
      if (editId) await api.put(`/notes/${editId}`, payload);
      else await api.post("/notes", payload);
      toast.success(t("save") + " ✓"); setOpen(false); setEditId(null); setForm(blank); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const openNew = () => { setForm({ ...blank, signature: user?.default_signature || "" }); setEditId(null); setSigKey((k) => k + 1); setOpen(true); };
  const openEdit = (n) => { setForm({ ...blank, ...n }); setEditId(n.id); setViewing(null); setSigKey((k) => k + 1); setOpen(true); };

  const duplicateNote = (n) => {
    setEditId(null); setViewing(null);
    const p = curPatient(n.patient_id);
    setForm({
      ...blank,
      patient_id: n.patient_id || "",
      content: n.content || "",
      icd10: n.icd10 || "", cpt_code: n.cpt_code || "", risk_level: n.risk_level || "",
      attending_provider: n.attending_provider || "",
      exequatur_number: n.exequatur_number || "",
      dob: p.dob || n.dob || "", ssn: p.ssn || n.ssn || "", gender: p.gender || n.gender || "",
      visit_date: new Date().toISOString().slice(0, 10),
      signature: user?.default_signature || "",
    });
    setCodeHistory({ icd10: [], cpt: [] });
    if (n.patient_id) api.get("/notes/patient-code-history", { params: { patient_id: n.patient_id } })
      .then((r) => setCodeHistory(r.data)).catch(() => {});
    setSigKey((k) => k + 1);
    setOpen(true);
    toast.success(t("duplicated"));
  };

  const deleteNote = async (n) => {
    try { await api.delete(`/notes/${n.id}`); toast.success(t("delete") + " ✓"); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    try { await bulkDelete("/notes/bulk-delete", [...sel.selected], t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const insertSavedSig = () => { setForm((f) => ({ ...f, signature: user.default_signature })); setSigKey((k) => k + 1); };
  const saveDefaultSig = async () => {
    if (!form.signature) { toast.error(t("providerSignature")); return; }
    setSavingSig(true);
    try { await api.put("/auth/signature", { signature: form.signature }); await refreshUser(); toast.success(t("signatureSaved")); }
    catch (err) { toast.error(apiErr(err)); }
    finally { setSavingSig(false); }
  };

  // Editable header (inline JSX, NOT a nested component — prevents input focus loss)
  const editableHeader = (
    <div>
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500 mb-2">{t("notesLabel")}</p>
      <div className="rounded-lg border border-border border-l-4 border-l-moneygreen-600 bg-white p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
          <HRow label={t("patientName")}>
            <select required value={form.patient_id} onChange={onPatient} className={headerInputCls} data-testid="nf-patient">
              <option value="">{t("selectPatient")}</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </HRow>
          <HRow label={t("dateOfSession")}><input type="date" value={form.visit_date || ""} onChange={set("visit_date")} className={headerInputCls} data-testid="nf-visit-date" /></HRow>
          <HRow label={t("dob")}><input type="date" value={form.dob || ""} onChange={set("dob")} className={headerInputCls} data-testid="nf-dob" /></HRow>
          <HRow label={t("socialSecurity")}><input value={form.ssn || ""} onChange={set("ssn")} className={headerInputCls} data-testid="nf-ssn" placeholder="XXX-XX-XXXX" /></HRow>
          <div>
            <HRow label={t("icd10Code")}><input value={form.icd10 || ""} onChange={set("icd10")} className={headerInputCls} data-testid="nf-icd10" placeholder="e.g. F33.0" /></HRow>
            {codeHistory.icd10.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-1 pl-2" data-testid="icd-suggestions">
                <span className="text-xs text-stone-400">{t("usedBefore")}:</span>
                {codeHistory.icd10.map((c) => (
                  <button key={c} type="button" onClick={() => setForm((f) => ({ ...f, icd10: c }))} data-testid={`icd-chip-${c}`}
                    className="text-xs px-2 py-0.5 rounded-full bg-moneygreen-100 text-moneygreen-700 hover:bg-moneygreen-200 font-mono font-semibold transition-colors">{c}</button>
                ))}
              </div>
            )}
          </div>
          <div>
            <HRow label={t("cptCode")}>
              <input list="cpt-list" value={form.cpt_code || ""} onChange={set("cpt_code")} className={headerInputCls} data-testid="nf-cpt" placeholder="e.g. 90837" />
              <datalist id="cpt-list">{cpt.map((c) => <option key={c.code} value={c.code}>{c.description}</option>)}</datalist>
            </HRow>
            {codeHistory.cpt.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-1 pl-2" data-testid="cpt-suggestions">
                <span className="text-xs text-stone-400">{t("usedBefore")}:</span>
                {codeHistory.cpt.map((c) => (
                  <button key={c} type="button" onClick={() => setForm((f) => ({ ...f, cpt_code: c }))} data-testid={`cpt-chip-${c}`}
                    className="text-xs px-2 py-0.5 rounded-full bg-tan-100 text-tan-900 hover:bg-tan-200 font-mono font-semibold transition-colors">{c}</button>
                ))}
              </div>
            )}
          </div>
          <HRow label={t("riskAssessment")}>
            <select value={form.risk_level || ""} onChange={set("risk_level")} className={headerInputCls} data-testid="nf-risk">
              <option value="">{t("selectRisk")}</option>
              {RISK_LEVELS.map((r) => <option key={r} value={r}>{t(riskKey[r])}</option>)}
            </select>
          </HRow>
          <HRow label={t("provider")}>
            <select value={form.attending_provider || ""} onChange={(e) => {
                const name = e.target.value;
                const prov = providers.find((u) => u.name === name);
                setForm((f) => ({ ...f, attending_provider: name,
                  exequatur_number: (prov && prov.exequatur_number) ? prov.exequatur_number : f.exequatur_number }));
              }} className={headerInputCls} data-testid="nf-provider">
              <option value="">{t("selectProvider")}</option>
              {providers.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
            </select>
          </HRow>
          <HRow label={t("exequaturNo")}>
            <input value={form.exequatur_number || ""} onChange={set("exequatur_number")} className={headerInputCls} data-testid="nf-exequatur" placeholder={t("exequaturPlaceholder")} />
          </HRow>
        </div>
      </div>
    </div>
  );

  // Print-only header rendered from the live form values (editor PDF)
  const printHeader = (
    <div>
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500 mb-2">{t("notesLabel")}</p>
      <div className="rounded-lg border border-border border-l-4 border-l-moneygreen-600 bg-white p-5">
        <div className="space-y-1 max-w-md text-sm">
          <ReadRow label={t("patientName")} value={patientName(form.patient_id)} />
          <ReadRow label={t("dob")} value={fmtDate(form.dob)} />
          <ReadRow label={t("socialSecurity")} value={form.ssn} />
          <ReadRow label={t("dateOfSession")} value={fmtDate(form.visit_date)} />
          <ReadRow label={t("icd10Code")} value={form.icd10} />
          <ReadRow label={t("cptCode")} value={form.cpt_code} />
          <ReadRow label={t("riskAssessment")} value={form.risk_level ? riskLabel(form.risk_level) : ""} />
          <ReadRow label={t("provider")} value={form.attending_provider} />
        </div>
      </div>
    </div>
  );

  // Read-only header (view modal & PDF for saved notes)
  const ReadHeader = ({ n }) => (
    <div>
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500 mb-2">{t("notesLabel")}</p>
      <div className="rounded-lg border border-border border-l-4 border-l-moneygreen-600 bg-white p-5">
        <div className="space-y-1 max-w-md text-sm">
          <ReadRow label={t("patientName")} value={<Private value={patientName(n.patient_id)} />} />
          <ReadRow label={t("dob")} value={<Private value={fmtDate(curPatient(n.patient_id).dob || n.dob)} />} />
          <ReadRow label={t("socialSecurity")} value={<Private value={curPatient(n.patient_id).ssn || n.ssn} />} />
          <ReadRow label={t("dateOfSession")} value={fmtDate(n.visit_date)} />
          <ReadRow label={t("icd10Code")} value={n.icd10} />
          <ReadRow label={t("cptCode")} value={n.cpt_code} />
          <ReadRow label={t("riskAssessment")} value={n.risk_level ? riskLabel(n.risk_level) : ""} />
          <ReadRow label={t("provider")} value={providerName(n)} />
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <PageHeader title={t("notes")} subtitle={`${filtered.length}`}
        action={
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border border-border overflow-hidden" data-testid="notes-view-toggle">
              <button onClick={() => setViewMode("cards")} data-testid="notes-view-cards" title={t("cardView")}
                className={`px-2.5 py-1.5 transition-colors ${viewMode === "cards" ? "bg-moneygreen-600 text-white" : "bg-white text-moneygreen-700 hover:bg-moneygreen-50"}`}>
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button onClick={() => setViewMode("list")} data-testid="notes-view-list" title={t("listView")}
                className={`px-2.5 py-1.5 transition-colors ${viewMode === "list" ? "bg-moneygreen-600 text-white" : "bg-white text-moneygreen-700 hover:bg-moneygreen-50"}`}>
                <List className="w-4 h-4" />
              </button>
            </div>
            {allowed && <Btn onClick={openNew} data-testid="add-note-btn"><Plus className="w-4 h-4" />{t("newNote")}</Btn>}
          </div>
        } />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex items-center gap-1.5 text-stone-500 text-sm font-semibold"><Filter className="w-4 h-4" />{t("filterBy")}:</div>
        <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} data-testid="notes-filter-provider" className={inputCls + " !w-auto"}>
          <option value="">{t("allProviders")}</option>
          {providerOptions.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)} data-testid="notes-filter-patient" className={inputCls + " !w-auto"}>
          <option value="">{t("allPatients")}</option>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
        </select>
        <div className="flex items-center gap-1">
          <input type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} data-testid="notes-filter-date"
            className={inputCls + " !w-auto"} title={t("filterDate")} />
          {dateFilter && (
            <button onClick={() => setDateFilter("")} data-testid="notes-clear-date-filter" title={t("filterDate")}
              className="p-1 rounded hover:bg-stone-100 text-stone-500"><X className="w-4 h-4" /></button>
          )}
        </div>
      </div>

      {allowed && filtered.length > 0 && (
        <div className="flex items-center gap-3 mb-4">
          <label className="flex items-center gap-1.5 text-sm text-stone-600 cursor-pointer">
            <input type="checkbox" data-testid="select-all-notes"
              checked={sel.count >= filtered.length && filtered.length > 0}
              onChange={() => sel.toggleAll(filtered.map((n) => n.id))}
              className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
            {t("selectAll")}
          </label>
          {sel.count > 0 && (<>
            <span className="text-sm text-stone-500">{sel.count}</span>
            <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-notes"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
            <Btn variant="outline" onClick={sel.clear} data-testid="deselect-notes">{t("deselectAll")}</Btn>
          </>)}
        </div>
      )}

      {filtered.length === 0 ? <Card><Empty text={t("noData")} /></Card> : viewMode === "list" ? (
        <Card className="overflow-hidden" data-testid="notes-list-table">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  {allowed && <th className="px-4 py-3 w-8"></th>}
                  <th className="px-5 py-3">{t("patient")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("dateOfSession")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("provider")}</th>
                  <th className="px-5 py-3 hidden lg:table-cell">ICD-10 / CPT</th>
                  <th className="px-5 py-3">{t("riskAssessment")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((n, i) => (
                  <tr key={n.id} data-testid={`note-row-${n.id}`} className={`border-b border-border/60 ${sel.has(n.id) ? "bg-moneygreen-50" : i % 2 ? "bg-tan-50/40" : ""}`}>
                    {allowed && (
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={sel.has(n.id)} onChange={() => sel.toggle(n.id)}
                          data-testid={`select-note-${n.id}`} className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                      </td>
                    )}
                    <td className="px-5 py-3 font-semibold text-moneygreen-800 cursor-pointer" onClick={() => setViewing(n)}><Private value={patientName(n.patient_id)} /></td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{providerName(n)}</td>
                    <td className="px-5 py-3 hidden lg:table-cell text-stone-500 font-mono text-xs">{[n.icd10, n.cpt_code].filter(Boolean).join(" / ") || "—"}</td>
                    <td className="px-5 py-3 text-stone-600">{n.risk_level ? riskLabel(n.risk_level) : "—"}</td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Btn variant="ghost" onClick={() => setViewing(n)} data-testid={`view-note-${n.id}`} className="!px-2" title={t("view")}><Eye className="w-4 h-4" /></Btn>
                        {allowed && <Btn variant="ghost" onClick={() => openEdit(n)} data-testid={`edit-note-${n.id}`} className="!px-2" title={t("edit")}><Pencil className="w-4 h-4" /></Btn>}
                        {allowed && <Btn variant="ghost" onClick={() => duplicateNote(n)} data-testid={`duplicate-note-${n.id}`} className="!px-2" title={t("duplicate")}><Copy className="w-4 h-4" /></Btn>}
                        {allowed && <Btn variant="ghost" onClick={() => deleteNote(n)} data-testid={`delete-note-${n.id}`} className="!px-2 !text-destructive" title={t("delete")}><Trash2 className="w-4 h-4" /></Btn>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtered.map((n, i) => (
            <motion.div key={n.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Card className={`p-5 ${sel.has(n.id) ? "ring-2 ring-moneygreen-500" : ""}`} data-testid={`note-card-${n.id}`}>
                <div className="flex items-start gap-3 mb-2">
                  {allowed && (
                    <input type="checkbox" checked={sel.has(n.id)} onChange={() => sel.toggle(n.id)}
                      data-testid={`select-note-${n.id}`} className="mt-1 w-4 h-4 accent-moneygreen-600 cursor-pointer shrink-0" />
                  )}
                  <div className="w-9 h-9 rounded-md bg-moneygreen-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-moneygreen-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-heading font-bold text-moneygreen-800 truncate"><Private value={patientName(n.patient_id)} /></p>
                    <p className="text-xs text-stone-500">{fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))} · {providerName(n)}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-stone-500 mb-2">
                  {n.icd10 && <span><b className="text-stone-600">ICD-10:</b> {n.icd10}</span>}
                  {n.cpt_code && <span><b className="text-stone-600">CPT:</b> {n.cpt_code}</span>}
                  {n.risk_level && <span><b className="text-stone-600">{t("riskAssessment")}:</b> {riskLabel(n.risk_level)}</span>}
                </div>
                <div className="text-sm text-stone-600 whitespace-pre-wrap line-clamp-4">{n.content}</div>
                {n.signature && (
                  <div className="mt-3 pt-3 border-t border-border">
                    <img src={n.signature} alt="signature" className="h-12 object-contain my-1" data-testid={`note-sig-${n.id}`} />
                    <p className="text-sm"><span className="font-bold text-moneygreen-800">{t("providerSignature")}</span> <span className="text-stone-500">· {fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))}</span></p>
                    {n.exequatur_number && <p className="text-xs text-stone-500" data-testid={`note-exequatur-${n.id}`}>{t("exequaturNo")}: {n.exequatur_number}</p>}
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-border flex justify-end gap-2">
                  <Btn variant="outline" onClick={() => setViewing(n)} data-testid={`view-note-${n.id}`}><Eye className="w-4 h-4" />{t("view")}</Btn>
                  {allowed && <Btn variant="outline" onClick={() => openEdit(n)} data-testid={`edit-note-${n.id}`}><Pencil className="w-4 h-4" />{t("edit")}</Btn>}
                  {allowed && <Btn variant="ghost" onClick={() => duplicateNote(n)} data-testid={`duplicate-note-${n.id}`} className="!px-2" title={t("duplicate")}><Copy className="w-4 h-4" /></Btn>}
                  {allowed && <Btn variant="ghost" onClick={() => deleteNote(n)} data-testid={`delete-note-${n.id}`} className="!px-2 !text-destructive" title={t("delete")}><Trash2 className="w-4 h-4" /></Btn>}
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      {/* New / Edit note */}
      <Modal open={open} onClose={() => { setOpen(false); setEditId(null); }} title={editId ? t("editNote") : t("newNote")} wide>
        <form onSubmit={save} className="space-y-4">
          <div id="note-print" className="space-y-4">
            <div className="rounded-lg border border-border p-4 no-print">
              <EditableLetterhead settings={settings} onSaved={setSettings} t={t}
                canEdit={["admin", "doctor", "nurse", "psychologist"].includes(user?.role)} />
            </div>
            <div className="print-only"><Letterhead settings={settings} /></div>
            <div className="no-print">{editableHeader}</div>
            <div className="print-only">{printHeader}</div>
            {/* Blank writing page */}
            <textarea value={form.content} onChange={set("content")} data-testid="nf-content"
              className="w-full min-h-[420px] p-6 bg-white border border-border rounded-lg text-base leading-relaxed text-stone-800 focus:outline-none focus:ring-2 focus:ring-moneygreen-500 no-print"
              placeholder={t("noteBodyPlaceholder")} />
            <div className="print-only whitespace-pre-wrap text-base leading-relaxed text-stone-800 p-6">{form.content}</div>
            {form.signature && (
              <div className="pt-3 border-t border-border">
                <img src={form.signature} alt="signature" className="h-14 object-contain my-1" />
                <p className="text-sm"><span className="font-bold text-moneygreen-800">{t("providerSignature")}</span> <span className="text-stone-500">· {fmtDate(form.visit_date)}</span></p>
                {form.exequatur_number && <p className="text-xs text-stone-500">{t("exequaturNo")}: {form.exequatur_number}</p>}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2 no-print flex-wrap">
            <Btn type="button" variant="outline" onClick={summarize} disabled={summarizing} data-testid="ai-summarize-btn">
              {summarizing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {summarizing ? t("summarizing") : t("aiSummarize")}
            </Btn>
            <Btn variant="outline" type="button" onClick={() => { if (editId) api.post(`/notes/${editId}/to-folder`).then(() => toast.success(t("savedToFolder"))).catch(() => {}); printSection("note-print"); }} data-testid="note-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
            <Btn variant="outline" type="button" onClick={() => printSection("note-print")} data-testid="note-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
          </div>

          <div className="p-4 rounded-md bg-tan-50 border border-tan-200 no-print">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5">
                <PenLine className="w-3.5 h-3.5" /> {t("providerSignature")}
              </p>
              <div className="flex items-center gap-2">
                {user?.default_signature && (
                  <Btn type="button" variant="outline" onClick={insertSavedSig} data-testid="insert-saved-sig-btn">
                    <Stamp className="w-4 h-4" />{t("insertMySignature")}
                  </Btn>
                )}
                <Btn type="button" variant="outline" onClick={saveDefaultSig} disabled={savingSig || !form.signature} data-testid="save-default-sig-btn">
                  {savingSig ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{t("saveAsMyDefault")}
                </Btn>
              </div>
            </div>
            <SignaturePad key={sigKey} value={form.signature} allowUpload
              onChange={(v) => setForm((f) => ({ ...f, signature: v }))} testid="note-signature" />
          </div>

          <div className="flex justify-end gap-2 pt-2 no-print">
            <Btn variant="outline" type="button" onClick={() => { setOpen(false); setEditId(null); }}>{t("cancel")}</Btn>
            <Btn type="submit" data-testid="save-note-btn">{t("save")}</Btn>
          </div>
        </form>
      </Modal>

      {/* View note */}
      <Modal open={!!viewing} onClose={() => setViewing(null)} title={viewing ? patientName(viewing.patient_id) : t("view")} wide>
        {viewing && (
          <div className="space-y-4">
            <div id="note-print" className="space-y-4">
              <Letterhead settings={settings} />
              <ReadHeader n={viewing} />
              <div className="whitespace-pre-wrap text-base leading-relaxed text-stone-800 p-6 border border-border rounded-lg min-h-[200px] no-print" data-testid="note-view-body">{viewing.content}</div>
              <div className="print-only whitespace-pre-wrap text-base leading-relaxed text-stone-800 p-6">{viewing.content}</div>
              {viewing.signature && (
                <div className="pt-3 border-t border-border">
                  <img src={viewing.signature} alt="signature" className="h-14 object-contain my-1" />
                  <p className="text-sm"><span className="font-bold text-moneygreen-800">{t("providerSignature")}</span> <span className="text-stone-500">· {fmtDate(viewing.visit_date)}</span></p>
                  {viewing.exequatur_number && <p className="text-xs text-stone-500" data-testid="view-note-exequatur">{t("exequaturNo")}: {viewing.exequatur_number}</p>}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2 no-print">
              <Btn variant="outline" onClick={() => { if (viewing?.id) api.post(`/notes/${viewing.id}/to-folder`).then(() => toast.success(t("savedToFolder"))).catch(() => {}); printSection("note-print"); }} data-testid="view-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
              <Btn variant="outline" onClick={() => printSection("note-print")} data-testid="view-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
              {allowed && <Btn onClick={() => openEdit(viewing)} data-testid="view-edit-btn"><Pencil className="w-4 h-4" />{t("edit")}</Btn>}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

const HRow = ({ label, children }) => (
  <div className="flex items-baseline gap-2">
    <span className="w-32 shrink-0 text-sm font-semibold text-stone-700 leading-tight">{label}:</span>
    <div className="flex-1 min-w-0">{children}</div>
  </div>
);

const ReadRow = ({ label, value }) => (
  <div className="flex items-baseline gap-2">
    <span className="w-40 shrink-0 font-semibold text-stone-700">{label}:</span>
    <span className="flex-1 text-moneygreen-800 font-medium">{value || "—"}</span>
  </div>
);
