import React, { useEffect, useMemo, useState, useRef } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { can } from "../lib/perms";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { Private } from "../context/PrivacyContext";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Btn, Badge, Empty, Card, inputCls } from "../components/ui-kit";
import { AddIcdCodeModal } from "../components/AddIcdCodeModal";
import { ManagedSelect } from "../components/ManagedSelect";
import { SignaturePad } from "../components/SignaturePad";
import { Letterhead, EditableLetterhead } from "../components/Letterhead";
import { printSection } from "../lib/print";
import { fmtDate, fmtDateTime } from "../lib/date";
import { Plus, Sparkles, Loader2, FileText, PenLine, Printer, FileDown, Eye, Pencil, Stamp, Save, Trash2, LayoutGrid, List, Copy, Filter, X, CheckCircle2, Download, ChevronDown, Receipt, XCircle, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

const RISK_LEVELS = ["Low", "Moderate", "High", "Imminent"];
const riskKey = { Low: "riskLow", Moderate: "riskModerate", High: "riskHigh", Imminent: "riskImminent" };
const asArray = (value) => (Array.isArray(value) ? value : []);

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
  const navigate = useNavigate();
  const canInvoice = can(user?.role, "invoices") || user?.role === "admin";
  const generateInvoice = (n) => navigate(`/invoices?from_note=${n.id}&patient_id=${n.patient_id || ""}`);
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
  const [billingStatusFilter, setBillingStatusFilter] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [editWasApproved, setEditWasApproved] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [savingSig, setSavingSig] = useState(false);
  const [codeHistory, setCodeHistory] = useState({ icd10: [], cpt: [] });
  const [manageOpen, setManageOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState("");
  const [replaceMap, setReplaceMap] = useState({});
  const [icdCatalog, setIcdCatalog] = useState([]);
  const [addIcdOpen, setAddIcdOpen] = useState(false);
  const [viewMode, setViewMode] = useState("cards");
  const [providerFilter, setProviderFilter] = useState("");
  const [patientFilter, setPatientFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [completeOnSign, setCompleteOnSign] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportStart, setExportStart] = useState("");
  const [exportEnd, setExportEnd] = useState("");
  const [icdHistOpen, setIcdHistOpen] = useState(false);
  const [cptHistOpen, setCptHistOpen] = useState(false);
  const [icdAllOpen, setIcdAllOpen] = useState(false);
  const [cptAllOpen, setCptAllOpen] = useState(false);
  const icdHistRef = useRef(null);
  const cptHistRef = useRef(null);
  const icdAllRef = useRef(null);
  const cptAllRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const response = await api.get("/notes");
      setNotes(asArray(response.data));
      setLoadError("");
    } catch (error) {
      setNotes([]);
      setLoadError(apiErr(error));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(asArray(r.data))).catch(() => setPatients([]));
    api.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
    api.get("/cpt-codes").then((r) => setCpt(asArray(r.data))).catch(() => setCpt([]));
    api.get("/icd-codes").then((r) => setIcdCatalog(asArray(r.data))).catch(() => setIcdCatalog([]));
    api.get("/users").then((r) => setProviders(asArray(r.data).filter((u) => ["doctor", "nurse", "psychologist", "admin"].includes(u.role) && u.provider_active !== false))).catch(() => setProviders([]));
  }, []);

  useEffect(() => {
    const onDown = (e) => {
      if (icdHistRef.current && !icdHistRef.current.contains(e.target)) setIcdHistOpen(false);
      if (cptHistRef.current && !cptHistRef.current.contains(e.target)) setCptHistOpen(false);
      if (icdAllRef.current && !icdAllRef.current.contains(e.target)) setIcdAllOpen(false);
      if (cptAllRef.current && !cptAllRef.current.contains(e.target)) setCptAllOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const patientName = (id) => {
    const p = patients.find((x) => x.id === id);
    return p ? `${p.first_name} ${p.last_name}` : "—";
  };
  const providerName = (n) => n.attending_provider || n.author || "—";
  const attestText = (prov, date) => `This Document has been electronically signed by ${prov || "Saday Rodriguez Cabrera"} on ${fmtDate(date)}.`;
  const riskLabel = (r) => (r ? t(riskKey[r] || r) : "—");
  const curPatient = (id) => patients.find((x) => x.id === id) || {};

  const noteProvider = (n) => n.attending_provider || n.author || "";
  const noteDate = (n) => n.visit_date || (n.created_at || "").slice(0, 10);
  const providerOptions = useMemo(() => (
    [...new Set([...providers.map((u) => u.name), ...notes.map(noteProvider)].filter(Boolean))]
  ), [providers, notes]);
  const billingStatus = (n) => n.billing_review_status || (n.signature ? "pending_review" : "unsigned");
  const filtered = useMemo(() => notes.filter((n) =>
    (!providerFilter || noteProvider(n) === providerFilter) &&
    (!patientFilter || n.patient_id === patientFilter) &&
    (!dateFilter || noteDate(n) === dateFilter) &&
    (!statusFilter || (statusFilter === "completed" ? !!n.completed : !n.completed)) &&
    (!billingStatusFilter || billingStatus(n) === billingStatusFilter)
  ), [notes, providerFilter, patientFilter, dateFilter, statusFilter, billingStatusFilter]);
  const tally = useMemo(() => {
    const done = notes.filter((n) => n.completed).length;
    return { total: notes.length, completed: done, open: notes.length - done };
  }, [notes]);

  const dismissIcd = async (code) => {
    const pid = form.patient_id;
    if (!pid) return;
    try {
      await api.post("/notes/patient-code-history/dismiss", { patient_id: pid, code });
      setCodeHistory((h) => ({ ...h, icd10: h.icd10.filter((c) => c !== code) }));
      toast.success(t("icdRemoved"));
    } catch { toast.error("Failed"); }
  };

  const reloadCodeHistory = () => {
    const pid = form.patient_id;
    if (pid) api.get("/notes/patient-code-history", { params: { patient_id: pid } })
      .then((r) => setCodeHistory(r.data)).catch(() => {});
  };

  const bulkFix = async (code, replacement) => {
    const pid = form.patient_id;
    if (!pid) return;
    if (!replacement && !window.confirm(t("confirmBulkRemove").replace("{code}", code))) return;
    setBulkBusy(code);
    try {
      const r = await api.post(`/patients/${pid}/icd-bulk`, { code, replacement: replacement || null });
      toast.success(t("bulkDone").replace("{n}", (r.data.notes_updated + r.data.invoices_updated)));
      setReplaceMap((m) => ({ ...m, [code]: "" }));
      reloadCodeHistory();
    } catch (e) { toast.error("Failed"); }
    finally { setBulkBusy(""); }
  };

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
      let noteId = editId;
      if (editId) await api.put(`/notes/${editId}`, payload);
      else { const r = await api.post("/notes", payload); noteId = r.data?.id; }
      if (noteId && form.signature && completeOnSign) {
        try { await api.put(`/notes/${noteId}/complete`, { completed: true }); } catch { /* best-effort */ }
      }
      toast.success(t("save") + " ✓"); setOpen(false); setEditId(null); setForm(blank); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const billingStatusMeta = {
    unsigned: { tone: "gray", key: "billingStatusUnsigned" },
    pending_review: { tone: "amber", key: "billingStatusPendingReview" },
    approved: { tone: "green", key: "billingStatusApproved" },
    needs_correction: { tone: "red", key: "billingStatusNeedsCorrection" },
  };
  const BillingBadge = ({ n, testid }) => {
    const meta = billingStatusMeta[billingStatus(n)] || billingStatusMeta.unsigned;
    return <Badge tone={meta.tone} data-testid={testid}>{t(meta.key)}</Badge>;
  };
  const billingReview = async (status) => {
    if (!viewing) return;
    setReviewing(true);
    try {
      const r = await api.put(`/notes/${viewing.id}/billing-review`, { status, note: reviewNote || null });
      setViewing(r.data);
      setNotes((ns) => ns.map((n) => (n.id === r.data.id ? r.data : n)));
      setReviewNote("");
      toast.success(t("billingReviewSaved"));
    } catch (err) { toast.error(apiErr(err)); }
    finally { setReviewing(false); }
  };
  useEffect(() => { setReviewNote(""); }, [viewing?.id]);

  const openNew = () => { setForm({ ...blank, signature: user?.default_signature || "" }); setEditId(null); setSigKey((k) => k + 1); setOpen(true); setEditWasApproved(false); };
  const openEdit = (n) => {
    setForm({ ...blank, ...n }); setEditId(n.id); setViewing(null); setSigKey((k) => k + 1); setOpen(true);
    setEditWasApproved(!!(n.signature || n.completed || billingStatus(n) === "approved"));
  };

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
  const toggleComplete = async (n) => {
    const next = !n.completed;
    try {
      await api.put(`/notes/${n.id}/complete`, { completed: next });
      setNotes((list) => list.map((x) => x.id === n.id
        ? { ...x, completed: next, completed_at: next ? new Date().toISOString() : null, completed_by: next ? (user?.name || "") : null }
        : x));
      toast.success(next ? t("noteCompleted") : t("noteReopened"));
    } catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    try { await bulkDelete("/notes/bulk-delete", [...sel.selected], t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };
  const completeSelected = async () => {
    const ids = [...sel.selected];
    try {
      const r = await api.post("/notes/bulk-complete", { ids });
      toast.success(t("notesCompleted").replace("{n}", r.data.updated));
      sel.clear(); load();
    } catch (err) { toast.error(apiErr(err)); }
  };
  const exportCompleted = async () => {
    try {
      const params = {};
      if (exportStart) params.start = exportStart;
      if (exportEnd) params.end = exportEnd;
      const res = await api.get("/notes/export-completed", { params, responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "completed_notes.csv";
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      setExportOpen(false);
    } catch (err) { toast.error(apiErr(err)); }
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
    <div data-testid="notes-editor-header">
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500 mb-2">{t("notesLabel")}</p>
      <div className="rounded-lg border border-border border-l-4 border-l-moneygreen-600 bg-white p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
          <HRow label={t("patientName")}>
            <ManagedSelect listKey="patients" required value={form.patient_id} onChange={onPatient} className={headerInputCls} data-testid="nf-patient">
              <option value="">{t("selectPatient")}</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </ManagedSelect>
          </HRow>
          <HRow label={t("dateOfSession")}><input type="date" value={form.visit_date || ""} onChange={set("visit_date")} className={headerInputCls} data-testid="nf-visit-date" /></HRow>
          <HRow label={t("dob")}><input type="date" value={form.dob || ""} onChange={set("dob")} className={headerInputCls} data-testid="nf-dob" /></HRow>
          <HRow label={t("socialSecurity")}><input value={form.ssn || ""} onChange={set("ssn")} className={headerInputCls} data-testid="nf-ssn" placeholder="XXX-XX-XXXX" /></HRow>
          <div>
            <HRow label={t("icd10Code")}>
              <div className="flex gap-1.5">
                <div className="relative flex-1" ref={icdHistRef}>
                  <button type="button" onClick={() => setIcdHistOpen((o) => !o)} data-testid="nf-icd10"
                    className={headerInputCls + " flex items-center justify-between text-left gap-1"}>
                    <span className={form.icd10 ? "font-mono truncate" : "text-stone-400 truncate"}>{form.icd10 || t("usedBefore")}</span>
                    <ChevronDown className="w-4 h-4 text-stone-400 shrink-0" />
                  </button>
                  {icdHistOpen && (
                    <div className="absolute z-30 mt-1 w-full bg-white border border-border rounded-md shadow-lg max-h-56 overflow-auto" data-testid="nf-icd-history-panel">
                      {codeHistory.icd10.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-stone-400">{t("noCodes")}</div>
                      ) : codeHistory.icd10.map((c) => (
                        <div key={c} className="flex items-center justify-between hover:bg-moneygreen-50">
                          <button type="button" onClick={() => { setForm((f) => ({ ...f, icd10: c })); setIcdHistOpen(false); }}
                            data-testid={`icd-opt-${c}`} className="flex-1 text-left px-3 py-1.5 font-mono text-sm text-moneygreen-800">{c}</button>
                          <button type="button" onClick={() => dismissIcd(c)} data-testid={`icd-opt-remove-${c}`} title={t("removeIcdSuggestion")}
                            className="px-2 py-1.5 text-stone-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                        </div>
                      ))}
                      <button type="button" onClick={() => { setManageOpen(true); setIcdHistOpen(false); }} data-testid="icd-manage-btn"
                        className="w-full text-left px-3 py-1.5 text-xs text-stone-500 border-t border-border hover:bg-stone-50">{t("manageCodes")}</button>
                    </div>
                  )}
                </div>
                <div className="relative" ref={icdAllRef}>
                  <button type="button" onClick={() => setIcdAllOpen((o) => !o)} title={t("allCodes")} data-testid="nf-icd10-add"
                    className="shrink-0 px-2 h-full rounded-md border border-moneygreen-600 text-moneygreen-700 hover:bg-moneygreen-50 transition-colors flex items-center"><Plus className="w-4 h-4" /></button>
                  {icdAllOpen && (
                    <div className="absolute z-30 mt-1 right-0 w-72 bg-white border border-border rounded-md shadow-lg max-h-64 overflow-auto" data-testid="nf-icd-all-panel">
                      {icdCatalog.map((c) => (
                        <button key={c.code} type="button" onClick={() => { setForm((f) => ({ ...f, icd10: c.code })); setIcdAllOpen(false); }}
                          data-testid={`nf-icd-all-${c.code}`} className="w-full text-left px-3 py-1.5 text-sm text-stone-700 hover:bg-moneygreen-50">
                          <span className="font-mono font-semibold text-moneygreen-800">{c.code}</span>{c.description ? ` — ${c.description}` : ""}
                        </button>
                      ))}
                      <button type="button" onClick={() => { setIcdAllOpen(false); setAddIcdOpen(true); }} data-testid="nf-icd-add-new"
                        className="w-full text-left px-3 py-1.5 text-xs text-moneygreen-700 font-semibold border-t border-border hover:bg-moneygreen-50 flex items-center gap-1"><Plus className="w-3.5 h-3.5" />{t("newIcdCode")}</button>
                    </div>
                  )}
                </div>
              </div>
            </HRow>
          </div>
          <div>
            <HRow label={t("cptCode")}>
              <div className="flex gap-1.5">
                <div className="relative flex-1" ref={cptHistRef}>
                  <button type="button" onClick={() => setCptHistOpen((o) => !o)} data-testid="nf-cpt"
                    className={headerInputCls + " flex items-center justify-between text-left gap-1"}>
                    <span className={form.cpt_code ? "font-mono truncate" : "text-stone-400 truncate"}>{form.cpt_code || t("usedBefore")}</span>
                    <ChevronDown className="w-4 h-4 text-stone-400 shrink-0" />
                  </button>
                  {cptHistOpen && (
                    <div className="absolute z-30 mt-1 w-full bg-white border border-border rounded-md shadow-lg max-h-56 overflow-auto" data-testid="nf-cpt-history-panel">
                      {codeHistory.cpt.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-stone-400">{t("noCodes")}</div>
                      ) : codeHistory.cpt.map((c) => (
                        <button key={c} type="button" onClick={() => { setForm((f) => ({ ...f, cpt_code: c })); setCptHistOpen(false); }}
                          data-testid={`cpt-opt-${c}`} className="w-full text-left px-3 py-1.5 font-mono text-sm text-moneygreen-800 hover:bg-moneygreen-50">{c}</button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="relative" ref={cptAllRef}>
                  <button type="button" onClick={() => setCptAllOpen((o) => !o)} title={t("allCodes")} data-testid="nf-cpt-add"
                    className="shrink-0 px-2 h-full rounded-md border border-moneygreen-600 text-moneygreen-700 hover:bg-moneygreen-50 transition-colors flex items-center"><Plus className="w-4 h-4" /></button>
                  {cptAllOpen && (
                    <div className="absolute z-30 mt-1 right-0 w-72 bg-white border border-border rounded-md shadow-lg max-h-64 overflow-auto" data-testid="nf-cpt-all-panel">
                      {cpt.map((c) => (
                        <button key={c.code} type="button" onClick={() => { setForm((f) => ({ ...f, cpt_code: c.code })); setCptAllOpen(false); }}
                          data-testid={`nf-cpt-all-${c.code}`} className="w-full text-left px-3 py-1.5 text-sm text-stone-700 hover:bg-moneygreen-50">
                          <span className="font-mono font-semibold text-moneygreen-800">{c.code}</span>{c.description ? ` — ${c.description}` : ""}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </HRow>
          </div>
          <HRow label={t("riskAssessment")}>
            <select value={form.risk_level || ""} onChange={set("risk_level")} className={headerInputCls} data-testid="nf-risk">
              <option value="">{t("selectRisk")}</option>
              {RISK_LEVELS.map((r) => <option key={r} value={r}>{t(riskKey[r])}</option>)}
            </select>
          </HRow>
          <HRow label={t("provider")}>
            <ManagedSelect listKey="providers" value={form.attending_provider || ""} onChange={(e) => {
                const name = e.target.value;
                const prov = providers.find((u) => u.name === name);
                setForm((f) => ({ ...f, attending_provider: name,
                  exequatur_number: (prov && prov.exequatur_number) ? prov.exequatur_number : f.exequatur_number }));
              }} className={headerInputCls} data-testid="nf-provider">
              <option value="">{t("selectProvider")}</option>
              {providers.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
            </ManagedSelect>
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
    <div data-testid="notes-page">
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
            {allowed && <Btn variant="outline" onClick={() => setExportOpen(true)} data-testid="export-completed-btn"><Download className="w-4 h-4" />{t("exportCompleted")}</Btn>}
            {allowed && <Btn onClick={openNew} data-testid="add-note-btn"><Plus className="w-4 h-4" />{t("newNote")}</Btn>}
          </div>
        } />

      {/* Status tally */}
      <div className="flex flex-wrap items-center gap-2 mb-3" data-testid="notes-tally">
        <button onClick={() => setStatusFilter("")} data-testid="tally-total"
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold border transition-colors ${!statusFilter ? "bg-stone-800 text-white border-stone-800" : "bg-white text-stone-600 border-border hover:bg-stone-50"}`}>
          <FileText className="w-3.5 h-3.5" />{t("notes")}: {tally.total}
        </button>
        <button onClick={() => setStatusFilter("open")} data-testid="tally-open"
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold border transition-colors ${statusFilter === "open" ? "bg-tan-600 text-white border-tan-600" : "bg-white text-tan-700 border-tan-300 hover:bg-tan-50"}`}>
          <PenLine className="w-3.5 h-3.5" />{t("openOnly")}: {tally.open}
        </button>
        <button onClick={() => setStatusFilter("completed")} data-testid="tally-completed"
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold border transition-colors ${statusFilter === "completed" ? "bg-moneygreen-600 text-white border-moneygreen-600" : "bg-white text-moneygreen-700 border-moneygreen-300 hover:bg-moneygreen-50"}`}>
          <CheckCircle2 className="w-3.5 h-3.5" />{t("completed")}: {tally.completed}
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex items-center gap-1.5 text-stone-500 text-sm font-semibold"><Filter className="w-4 h-4" />{t("filterBy")}:</div>
        <ManagedSelect listKey="providers" value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} data-testid="notes-filter-provider" className={inputCls + " !w-auto"}>
          <option value="">{t("allProviders")}</option>
          {providerOptions.map((p) => <option key={p} value={p}>{p}</option>)}
        </ManagedSelect>
        <ManagedSelect listKey="patients" value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)} data-testid="notes-filter-patient" className={inputCls + " !w-auto"}>
          <option value="">{t("allPatients")}</option>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
        </ManagedSelect>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="notes-filter-status" className={inputCls + " !w-auto"}>
          <option value="">{t("allStatuses")}</option>
          <option value="open">{t("openOnly")}</option>
          <option value="completed">{t("completedOnly")}</option>
        </select>
        <div className="flex items-center gap-1">
          <input type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} data-testid="notes-filter-date"
            className={inputCls + " !w-auto"} title={t("filterDate")} />
          {dateFilter && (
            <button onClick={() => setDateFilter("")} data-testid="notes-clear-date-filter" title={t("filterDate")}
              className="p-1 rounded hover:bg-stone-100 text-stone-500"><X className="w-4 h-4" /></button>
          )}
        </div>
        <select value={billingStatusFilter} onChange={(e) => setBillingStatusFilter(e.target.value)}
          data-testid="notes-filter-billing-status" className={inputCls + " !w-auto"} title={t("filterBillingStatus")}>
          <option value="">{t("allBillingStatuses")}</option>
          <option value="unsigned">{t("billingStatusUnsigned")}</option>
          <option value="pending_review">{t("billingStatusPendingReview")}</option>
          <option value="approved">{t("billingStatusApproved")}</option>
          <option value="needs_correction">{t("billingStatusNeedsCorrection")}</option>
        </select>
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
            <Btn variant="primary" onClick={completeSelected} data-testid="bulk-complete-notes"><CheckCircle2 className="w-4 h-4" />{t("completeSelected")}</Btn>
            <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-notes"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
            <Btn variant="outline" onClick={sel.clear} data-testid="deselect-notes">{t("deselectAll")}</Btn>
          </>)}
        </div>
      )}

      {loadError ? (
        <Card className="p-6 text-center text-red-700" data-testid="notes-load-error">
          <p className="font-semibold">{loadError}</p>
          <Btn variant="outline" className="mt-3" onClick={load}>{t("refresh")}</Btn>
        </Card>
      ) : loading ? (
        <Card className="p-10 flex justify-center" data-testid="notes-loading">
          <Loader2 className="w-6 h-6 animate-spin text-moneygreen-600" />
        </Card>
      ) : filtered.length === 0 ? <Card><Empty text={t("noData")} /></Card> : viewMode === "list" ? (
        <Card className="overflow-hidden" data-testid="notes-list-table">
                  <th className="px-5 py-3">{t("filterBillingStatus")}</th>
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
                  <th className="px-5 py-3 hidden md:table-cell">{t("completed")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((n, i) => (
                  <tr key={n.id} data-testid={`note-row-${n.id}`} className={`border-b border-border/60 ${n.completed ? "bg-moneygreen-100/70" : sel.has(n.id) ? "bg-moneygreen-50" : i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-5 py-3"><BillingBadge n={n} testid={`note-billing-status-${n.id}`} /></td>
                    {allowed && (
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={sel.has(n.id)} onChange={() => sel.toggle(n.id)}
                          data-testid={`select-note-${n.id}`} className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                      </td>
                    )}
                    <td className="px-5 py-3 font-semibold text-moneygreen-800 cursor-pointer" onClick={() => setViewing(n)}>
                      <Private value={patientName(n.patient_id)} />
                      {n.completed && <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-moneygreen-600 text-white text-[10px] font-bold uppercase tracking-wide align-middle" data-testid={`note-completed-badge-${n.id}`}><CheckCircle2 className="w-3 h-3" />{t("completed")}</span>}
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{providerName(n)}</td>
                    <td className="px-5 py-3 hidden lg:table-cell text-stone-500 font-mono text-xs">{`${n.icd10 || t("notRecorded")} / ${n.cpt_code || t("notRecorded")}`}</td>
                    <td className="px-5 py-3 text-stone-600">{n.risk_level ? riskLabel(n.risk_level) : "—"}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-xs" data-testid={`note-completed-cell-${n.id}`}>
                      {n.completed ? (
                        <span className="text-moneygreen-700">{fmtDate((n.completed_at || "").slice(0, 10))}{n.completed_by ? ` · ${n.completed_by}` : ""}</span>
                      ) : <span className="text-stone-400">—</span>}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Btn variant="ghost" onClick={() => setViewing(n)} data-testid={`view-note-${n.id}`} className="!px-2" title={t("view")}><Eye className="w-4 h-4" /></Btn>
                        {allowed && <Btn variant="ghost" onClick={() => toggleComplete(n)} data-testid={`complete-note-${n.id}`} className={`!px-2 ${n.completed ? "!text-moneygreen-600" : "!text-stone-400"}`} title={n.completed ? t("reopenNote") : t("markComplete")}><CheckCircle2 className="w-4 h-4" /></Btn>}
                        {allowed && <Btn variant="ghost" onClick={() => openEdit(n)} data-testid={`edit-note-${n.id}`} className="!px-2" title={t("edit")}><Pencil className="w-4 h-4" /></Btn>}
                        {canInvoice && <Btn variant="ghost" onClick={() => generateInvoice(n)} data-testid={`generate-invoice-${n.id}`} className="!px-2 !text-moneygreen-700" title={t("generateInvoice")}><Receipt className="w-4 h-4" /></Btn>}
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
              <Card className={`p-5 ${n.completed ? "ring-2 ring-moneygreen-500 bg-moneygreen-50/60" : sel.has(n.id) ? "ring-2 ring-moneygreen-500" : ""}`} data-testid={`note-card-${n.id}`}>
                <div className="flex items-start gap-3 mb-2">
                  {allowed && (
                    <input type="checkbox" checked={sel.has(n.id)} onChange={() => sel.toggle(n.id)}
                      data-testid={`select-note-${n.id}`} className="mt-1 w-4 h-4 accent-moneygreen-600 cursor-pointer shrink-0" />
                  )}
                  <div className="w-9 h-9 rounded-md bg-moneygreen-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-moneygreen-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-heading font-bold text-moneygreen-800 truncate"><Private value={patientName(n.patient_id)} /></p>
                    <p className="text-xs text-stone-500">{fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))} · {providerName(n)}</p>
                  </div>
                  <BillingBadge n={n} testid={`note-billing-status-${n.id}`} />
                  {n.completed && <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-moneygreen-600 text-white text-[10px] font-bold uppercase tracking-wide shrink-0 self-start" data-testid={`note-completed-badge-${n.id}`}><CheckCircle2 className="w-3 h-3" />{t("completed")}</span>}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-stone-500 mb-2">
                  <span><b className="text-stone-600">ICD-10:</b> {n.icd10 || t("notRecorded")}</span>
                  <span><b className="text-stone-600">CPT:</b> {n.cpt_code || t("notRecorded")}</span>
                  {n.risk_level && <span><b className="text-stone-600">{t("riskAssessment")}:</b> {riskLabel(n.risk_level)}</span>}
                </div>
                <div className="text-sm text-stone-600 whitespace-pre-wrap line-clamp-4">{n.content}</div>
                {n.completed && (
                  <p className="mt-2 text-xs text-moneygreen-700 flex items-center gap-1.5" data-testid={`note-completed-info-${n.id}`}>
                    <CheckCircle2 className="w-3.5 h-3.5" />{t("completed")}: {fmtDate((n.completed_at || "").slice(0, 10))}{n.completed_by ? ` · ${n.completed_by}` : ""}
                  </p>
                )}
                {n.signature && (
                  <div className="mt-3 pt-3 border-t border-border">
                    <img src={n.signature} alt="signature" className="h-12 object-contain my-1" data-testid={`note-sig-${n.id}`} />
                    <p className="text-sm font-bold text-moneygreen-800">{t("providerSignature")}</p>
                    {n.exequatur_number && <p className="text-xs text-stone-600" data-testid={`note-exequatur-${n.id}`}>Exequatur Num: {n.exequatur_number}</p>}
                    <p className="text-xs text-stone-500">{fmtDate(n.visit_date || (n.created_at || "").slice(0, 10))}</p>
                    <p className="text-[11px] text-stone-400 italic mt-1" data-testid={`note-attestation-${n.id}`}>{attestText(n.attending_provider, n.visit_date)}</p>
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-border flex justify-end gap-2">
                  <Btn variant="outline" onClick={() => setViewing(n)} data-testid={`view-note-${n.id}`}><Eye className="w-4 h-4" />{t("view")}</Btn>
                  {allowed && <Btn variant={n.completed ? "primary" : "outline"} onClick={() => toggleComplete(n)} data-testid={`complete-note-${n.id}`} title={n.completed ? t("reopenNote") : t("markComplete")}><CheckCircle2 className="w-4 h-4" />{n.completed ? t("reopenNote") : t("markComplete")}</Btn>}
                  {allowed && <Btn variant="outline" onClick={() => openEdit(n)} data-testid={`edit-note-${n.id}`}><Pencil className="w-4 h-4" />{t("edit")}</Btn>}
                  {canInvoice && <Btn variant="outline" onClick={() => generateInvoice(n)} data-testid={`generate-invoice-card-${n.id}`}><Receipt className="w-4 h-4" />{t("generateInvoice")}</Btn>}
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
          {editWasApproved && (
            <div className="p-3 rounded-md bg-amber-50 border border-amber-200 text-xs text-amber-800 no-print" data-testid="edit-approved-warning">
              {t("editApprovedWarning")}
              <label className="flex items-center gap-2 mt-2 font-medium cursor-pointer">
                <input type="checkbox" checked={!!form.title_nonclinical_confirmed} data-testid="title-nonclinical-confirm"
                  onChange={(e) => setForm({ ...form, title_nonclinical_confirmed: e.target.checked })} className="w-4 h-4 accent-moneygreen-600" />
                {t("titleNonClinicalConfirm")}
              </label>
            </div>
          )}
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
                <p className="text-sm font-bold text-moneygreen-800">{t("providerSignature")}</p>
                {form.exequatur_number && <p className="text-xs text-stone-600">Exequatur Num: {form.exequatur_number}</p>}
                <p className="text-xs text-stone-500">{fmtDate(form.visit_date)}</p>
                <p className="text-[11px] text-stone-400 italic mt-1">{attestText(form.attending_provider, form.visit_date)}</p>
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
            <label className={`mt-3 flex items-center gap-2 text-sm cursor-pointer ${form.signature ? "text-moneygreen-800" : "text-stone-400"}`}>
              <input type="checkbox" checked={completeOnSign} onChange={(e) => setCompleteOnSign(e.target.checked)}
                data-testid="nf-complete-on-sign" className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
              <CheckCircle2 className="w-4 h-4" />{t("completeOnSign")}
            </label>
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
                  <p className="text-sm font-bold text-moneygreen-800">{t("providerSignature")}</p>
                  {viewing.exequatur_number && <p className="text-xs text-stone-600" data-testid="view-note-exequatur">Exequatur Num: {viewing.exequatur_number}</p>}
                  <p className="text-xs text-stone-500">{fmtDate(viewing.visit_date)}</p>
                  <p className="text-[11px] text-stone-400 italic mt-1" data-testid="view-note-attestation">{attestText(viewing.attending_provider, viewing.visit_date)}</p>
                </div>
              )}
            </div>

            <div className="p-4 rounded-md bg-tan-50 border border-tan-200 no-print" data-testid="billing-review-panel">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <p className="text-xs font-bold uppercase tracking-wider text-moneygreen-600 flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5" /> {t("billingReview")}
                </p>
                <BillingBadge n={viewing} testid="view-billing-status" />
              </div>
              <p className="text-xs text-stone-500 mb-3">{t("billingReviewHint")}</p>
              {viewing.billing_reviewed_by && (
                <p className="text-xs text-stone-600 mb-3" data-testid="billing-reviewed-meta">
                  {t("billingReviewedBy")} <span className="font-semibold">{viewing.billing_reviewed_by}</span>
                  {" · "}{fmtDateTime(viewing.billing_reviewed_at)}
                  {viewing.billing_review_note && <> — "{viewing.billing_review_note}"</>}
                </p>
              )}
              {viewing.history && viewing.history.length > 0 && (
                <details className="mb-3 text-xs text-stone-500" data-testid="billing-review-history">
                  <summary className="cursor-pointer font-semibold text-stone-600">{t("reviewHistory")} ({viewing.history.length})</summary>
                  <div className="mt-2 space-y-2 pl-3 border-l-2 border-tan-300">
                    {[...viewing.history].reverse().map((h, i) => (
                      <div key={i}>
                        <p>{fmtDateTime(h.archived_at)} — {h.archived_reason === "re-signed" ? t("historyResigned") : t("historyEditedAfterApproval")}</p>
                        {h.billing_reviewed_by && (
                          <p>{t("billingReviewedBy")} {h.billing_reviewed_by} · {fmtDateTime(h.billing_reviewed_at)}
                            {h.billing_review_note && <> — "{h.billing_review_note}"</>}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}
              {user?.role === "admin" && (
                viewing.signature ? (
                  <div className="space-y-2">
                    <input value={reviewNote} onChange={(e) => setReviewNote(e.target.value)}
                      placeholder={t("billingReviewNotePlaceholder")} className={inputCls} data-testid="billing-review-note-input" />
                    <div className="flex flex-wrap gap-2">
                      <Btn type="button" onClick={() => billingReview("approved")} disabled={reviewing} data-testid="billing-approve-btn">
                        {reviewing ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}{t("approveForBilling")}
                      </Btn>
                      <Btn type="button" variant="outline" onClick={() => billingReview("needs_correction")} disabled={reviewing} data-testid="billing-needs-correction-btn">
                        <XCircle className="w-4 h-4" />{t("markNeedsCorrection")}
                      </Btn>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-stone-400 italic">{t("signFirstToReview")}</p>
                )
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2 no-print">
              <Btn variant="outline" onClick={() => { if (viewing?.id) api.post(`/notes/${viewing.id}/to-folder`).then(() => toast.success(t("savedToFolder"))).catch(() => {}); printSection("note-print"); }} data-testid="view-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
              <Btn variant="outline" onClick={() => printSection("note-print")} data-testid="view-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
              {allowed && <Btn onClick={() => openEdit(viewing)} data-testid="view-edit-btn"><Pencil className="w-4 h-4" />{t("edit")}</Btn>}
              {canInvoice && <Btn variant="outline" onClick={() => generateInvoice(viewing)} data-testid="view-generate-invoice-btn"><Receipt className="w-4 h-4" />{t("generateInvoice")}</Btn>}
            </div>
          </div>
        )}
      </Modal>

      <Modal open={manageOpen} onClose={() => setManageOpen(false)} title={t("manageCodesTitle")}>
        <p className="text-sm text-stone-500 mb-3">{t("manageCodesHint")}</p>
        {codeHistory.icd10.length === 0 ? <Empty text={t("noCodes")} /> : (
          <div className="space-y-2" data-testid="icd-manage-list">
            {codeHistory.icd10.map((c) => (
              <div key={c} className="flex items-center gap-2 p-2 rounded-lg border border-border bg-tan-50/40">
                <span className="font-mono font-bold text-moneygreen-800 w-24 shrink-0">{c}</span>
                <input value={replaceMap[c] || ""} onChange={(e) => setReplaceMap((m) => ({ ...m, [c]: e.target.value }))}
                  placeholder={t("replaceWith")} className={inputCls} data-testid={`icd-replace-input-${c}`} />
                <Btn variant="outline" onClick={() => bulkFix(c, (replaceMap[c] || "").trim())} disabled={!(replaceMap[c] || "").trim() || bulkBusy === c}
                  data-testid={`icd-replace-btn-${c}`} className="!px-3 shrink-0">{bulkBusy === c ? <Loader2 className="w-4 h-4 animate-spin" /> : t("replace")}</Btn>
                <Btn variant="ghost" onClick={() => bulkFix(c, "")} disabled={!!bulkBusy}
                  data-testid={`icd-bulk-remove-${c}`} className="!px-2 !text-destructive shrink-0" title={t("removeFromAllRecords")}><Trash2 className="w-4 h-4" /></Btn>
              </div>
            ))}
          </div>
        )}
        <div className="flex justify-end pt-4">
          <Btn variant="outline" onClick={() => setManageOpen(false)}>{t("close")}</Btn>
        </div>
      </Modal>

      <AddIcdCodeModal open={addIcdOpen} onClose={() => setAddIcdOpen(false)}
        onAdded={(c) => { setIcdCatalog((list) => [...list, c]); setForm((f) => ({ ...f, icd10: c.code })); }} />

      <Modal open={exportOpen} onClose={() => setExportOpen(false)} title={t("exportCompleted")}>
        <p className="text-sm text-stone-500 mb-4">{t("exportCompletedHint")}</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-stone-500 mb-1 block">{t("fromDate")}</label>
            <input type="date" value={exportStart} onChange={(e) => setExportStart(e.target.value)} data-testid="export-start" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-semibold text-stone-500 mb-1 block">{t("toDate")}</label>
            <input type="date" value={exportEnd} onChange={(e) => setExportEnd(e.target.value)} data-testid="export-end" className={inputCls} />
          </div>
        </div>
        <p className="text-xs text-stone-400 mt-2">{t("exportAllHint")}</p>
        <div className="flex justify-end gap-2 pt-4">
          <Btn variant="outline" onClick={() => setExportOpen(false)}>{t("cancel")}</Btn>
          <Btn onClick={exportCompleted} data-testid="export-confirm-btn"><Download className="w-4 h-4" />{t("exportCsv")}</Btn>
        </div>
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
