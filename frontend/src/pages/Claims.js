import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { ManagedSelect } from "../components/ManagedSelect";
import { fmtDate } from "../lib/date";
import {
  FolderArchive, Plus, Pencil, Trash2, ChevronLeft, Download, FileText,
  ReceiptText, Upload, FilePlus, CalendarClock, Eye, FolderInput, Send, ArrowUp, ArrowDown,
  Loader2, ShieldAlert, ShieldCheck, AlertTriangle, Wand2,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";

const sourceIcon = { form: FileText, invoice: ReceiptText, upload: Upload, note: FileText };
const sourceTone = { form: "green", invoice: "amber", upload: "tan", note: "green" };
const categoryLabelKey = {
  cover_sheet: "catCoverSheet", invoice: "catInvoice", progress_note: "catProgressNote",
  va_disability_letter: "catVaLetter", fmp_registration: "catFmpRegistration",
  provider_exequatur: "catExequatur", provider_diploma: "catDiploma",
};
const blankForm = { name: "", patient_id: "", claim_number: "", status: "draft", notes: "",
  va_claim_number: "", veteran_physical_address: "", veteran_mailing_address: "", diagnosis_narrative: "", payment_to: "provider" };

const VAL_TONE = {
  blocked: { border: "border-l-red-500", bg: "bg-red-50", icon: ShieldAlert, iconCls: "text-red-600", label: "validationBlocked" },
  review: { border: "border-l-amber-500", bg: "bg-amber-50", icon: AlertTriangle, iconCls: "text-amber-600", label: "validationReview" },
  ready: { border: "border-l-moneygreen-500", bg: "bg-moneygreen-50", icon: ShieldCheck, iconCls: "text-moneygreen-600", label: "validationReady" },
};

const CHIP_TONE = {
  blocked: { cls: "bg-red-100 text-red-700 border-red-200", icon: ShieldAlert, label: "chipBlocked" },
  review: { cls: "bg-amber-100 text-amber-700 border-amber-200", icon: AlertTriangle, label: "chipReview" },
  ready: { cls: "bg-moneygreen-100 text-moneygreen-700 border-moneygreen-200", icon: ShieldCheck, label: "chipReady" },
};

function ValChip({ v, t }) {
  if (!v) return <span className="text-stone-300">—</span>;
  const c = CHIP_TONE[v.status] || CHIP_TONE.review;
  const Icon = c.icon;
  const n = (v.issues || []).length;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-semibold ${c.cls}`}
      data-testid="claim-val-chip" title={(v.issues || []).map((i) => i.message).join("\n")}>
      <Icon className="w-3.5 h-3.5" />{t(c.label)}{v.status !== "ready" && n ? ` · ${n}` : ""}
    </span>
  );
}

function ClaimValidation({ v, t, onFix, fixing }) {
  const cfg = VAL_TONE[v.status] || VAL_TONE.review;
  const Icon = cfg.icon;
  return (
    <Card className={`p-4 mb-5 border-l-4 ${cfg.border} ${cfg.bg}`} data-testid="claim-validation">
      <div className="flex items-center gap-2">
        <Icon className={`w-5 h-5 ${cfg.iconCls}`} />
        <p className="font-semibold text-stone-800" data-testid="claim-validation-status">{t(cfg.label)}</p>
      </div>
      {v.issues?.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {v.issues.map((iss, i) => (
            <li key={i} className="flex items-start gap-2 text-sm" data-testid={`claim-validation-issue-${i}`}>
              <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${iss.level === "blocked" ? "bg-red-500" : "bg-amber-500"}`} />
              <span className="text-stone-700">{iss.message}</span>
            </li>
          ))}
        </ul>
      )}
      {v.fix?.type === "set_claim_date" && (
        <div className="mt-3">
          <Btn variant="outline" onClick={onFix} disabled={fixing} data-testid="claim-validation-fix-date"
            className="!border-moneygreen-500 !text-moneygreen-700 hover:!bg-moneygreen-100">
            {fixing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {t("fixSetClaimDate")} {fmtDate(v.fix.date)}
          </Btn>
        </div>
      )}
      {v.status === "blocked" && <p className="mt-3 text-xs font-medium text-red-700">{t("blockedCannotFinalize")}</p>}
    </Card>
  );
}

export default function Claims() {
  const { t } = useLang();
  const [packets, setPackets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankForm);
  const [patients, setPatients] = useState([]);
  const [forms, setForms] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [notes, setNotes] = useState([]);
  const [pickForm, setPickForm] = useState("");
  const [pickInvoice, setPickInvoice] = useState("");
  const [pickNote, setPickNote] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const [fromDateOpen, setFromDateOpen] = useState(false);
  const [fromDate, setFromDate] = useState({ patient_id: "", date: "" });
  const [datePatients, setDatePatients] = useState([]);
  const [datePatientsLoading, setDatePatientsLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [preview, setPreview] = useState(null);
  const [renameItem, setRenameItem] = useState(null);
  const [sendOpen, setSendOpen] = useState(false);
  const [sendTo, setSendTo] = useState("");
  const [sendBusy, setSendBusy] = useState(false);
  const [deleting, setDeleting] = useState("");
  const [packetBuilding, setPacketBuilding] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [checkFilter, setCheckFilter] = useState("all");
  const [bulkSel, setBulkSel] = useState([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);

  const SEV = { blocked: 0, review: 1, ready: 2 };
  const bulkEligible = (p) => p.ready_to_approve && !p.cover_review;
  const visiblePackets = [...packets]
    .filter((p) => checkFilter === "all" || (checkFilter === "approvable" ? p.ready_to_approve : (p.validation?.status || "review") === checkFilter))
    .sort((a, b) => (SEV[a.validation?.status] ?? 1) - (SEV[b.validation?.status] ?? 1));
  const eligibleVisible = checkFilter === "approvable" ? visiblePackets.filter(bulkEligible) : [];
  const toggleBulk = (id) => setBulkSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const runBulkApprove = async () => {
    setBulkBusy(true);
    try {
      const r = await api.post("/claims/bulk-approve", { ids: bulkSel });
      setBulkResult(r.data); setBulkSel([]);
      if (r.data.approved.length) toast.success(`${t("approvedLabel")}: ${r.data.approved.length}`);
      load();
    } catch (e) { toast.error(apiErr(e)); }
    finally { setBulkBusy(false); }
  };
  const checkCounts = packets.reduce((acc, p) => {
    const s = p.validation?.status || "review";
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  const load = useCallback(async () => {
    try { setPackets((await api.get("/claims")).data); } catch (e) { toast.error(apiErr(e)); }
  }, []);

  useEffect(() => {
    load();
    api.get("/claims/options/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/claims/options/forms").then((r) => setForms(r.data)).catch(() => {});
    api.get("/claims/options/invoices").then((r) => setInvoices(r.data)).catch(() => {});
    api.get("/claims/options/notes").then((r) => setNotes(r.data)).catch(() => {});
  }, [load]);

  const refreshSelected = async (cid) => {
    try { setSelected((await api.get(`/claims/${cid}`)).data); } catch (e) { toast.error(apiErr(e)); }
  };

  const fixClaimDate = async () => {
    setFixing(true);
    try {
      const r = await api.post(`/claims/${selected.id}/fix-date`, {});
      setSelected(r.data);
      toast.success(t("dateFixed"));
      load();
    } catch (e) { toast.error(apiErr(e)); }
    finally { setFixing(false); }
  };

  const openNew = () => { setEditing(null); setForm(blankForm); setModalOpen(true); };
  const openEdit = (p) => {
    setEditing(p);
    setForm({ name: p.name || "", patient_id: p.patient_id || "", claim_number: p.claim_number || "",
      status: p.status || "draft", notes: p.notes || "",
      va_claim_number: p.va_claim_number || "", veteran_physical_address: p.veteran_physical_address || "",
      veteran_mailing_address: p.veteran_mailing_address || "", diagnosis_narrative: p.diagnosis_narrative || "",
      payment_to: p.payment_to || "provider" });
    setModalOpen(true);
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const buildName = (pid, dateStr) => {
    const p = patients.find((x) => x.id === pid);
    return [p ? p.name : "", fmtDate(dateStr), "FMP Claim"].filter(Boolean).join(" ");
  };
  const setClaimPatient = (e) => {
    const pid = e.target.value;
    setForm((f) => ({ ...f, patient_id: pid, name: buildName(pid, f.claim_number) }));
  };
  const setClaimDate = (e) => {
    const v = e.target.value;
    setForm((f) => ({ ...f, claim_number: v, name: buildName(f.patient_id, v) }));
  };

  const save = async (e) => {
    e.preventDefault();
    const payload = { ...form, patient_id: form.patient_id || null, claim_number: form.claim_number || null };
    try {
      if (editing) {
        const r = await api.put(`/claims/${editing.id}`, payload);
        if (selected?.id === editing.id) setSelected(r.data);
      } else {
        await api.post("/claims", payload);
      }
      toast.success(t("packetSaved"));
      setModalOpen(false); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const remove = async (id) => {
    if (!window.confirm(t("confirmDeletePacket"))) return;
    const key = `claim:${id}`;
    setDeleting(key);
    try {
      const r = await api.delete(`/claims/${id}`);
      if (r.data.cleanup_pending) toast.warning(t("cleanupPendingWarning"), { duration: Infinity });
      else toast.success(t("delete") + " ✓");
      load();
    } catch (e) { toast.error(apiErr(e), { duration: Infinity }); }
    finally { setDeleting(""); }
  };

  const pickFromDateDate = async (e) => {
    const date = e.target.value;
    setFromDate({ patient_id: "", date });
    setDatePatients([]);
    if (!date) return;
    setDatePatientsLoading(true);
    try {
      const r = await api.get("/claims/options/patients-by-date", { params: { date } });
      setDatePatients(r.data);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setDatePatientsLoading(false); }
  };

  const closeFromDate = () => {
    setFromDateOpen(false);
    setFromDate({ patient_id: "", date: "" });
    setDatePatients([]);
  };

  const buildFromDate = async (e) => {
    e.preventDefault();
    if (!fromDate.patient_id || !fromDate.date) return;
    setBuilding(true);
    try {
      const r = await api.post("/claims/from-date", fromDate);
      toast.success(t("packetSaved"));
      closeFromDate();
      load();
      setSelected(r.data);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setBuilding(false); }
  };

  const attachForm = async () => {
    if (!pickForm) return;
    try { setSelected((await api.post(`/claims/${selected.id}/attach-form`, { form_id: pickForm })).data); setPickForm(""); }
    catch (e) { toast.error(apiErr(e)); }
  };
  const attachInvoice = async () => {
    if (!pickInvoice) return;
    try { setSelected((await api.post(`/claims/${selected.id}/attach-invoice`, { invoice_id: pickInvoice })).data); setPickInvoice(""); }
    catch (e) { toast.error(apiErr(e)); }
  };
  const attachNote = async () => {
    if (!pickNote) return;
    try { setSelected((await api.post(`/claims/${selected.id}/attach-note`, { note_id: pickNote })).data); setPickNote(""); }
    catch (e) { toast.error(apiErr(e)); }
  };
  const onUpload = async (e, category = "") => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (category) fd.append("category", category);
    setBusy(true);
    try {
      setSelected((await api.post(`/claims/${selected.id}/upload`, fd, { headers: { "Content-Type": "multipart/form-data" } })).data);
      toast.success(t(category === "cover_sheet" ? "uploadCoverSheet" : "uploadDocument") + " ✓");
    } catch (err) { toast.error(apiErr(err)); }
    finally { setBusy(false); e.target.value = ""; }
  };
  const removeItem = async (itemId) => {
    if (!window.confirm(t("confirmRemoveClaimItem"))) return;
    const key = `item:${itemId}`;
    setDeleting(key);
    try {
      const r = await api.delete(`/claims/${selected.id}/items/${itemId}`);
      setSelected(r.data);
      if (r.data.cleanup_pending) toast.warning(t("cleanupPendingWarning"), { duration: Infinity });
      else toast.success(t("delete") + " ✓");
    } catch (e) { toast.error(apiErr(e), { duration: Infinity }); }
    finally { setDeleting(""); }
  };

  const authedDownload = async (url, fallbackName) => {
    try {
      const r = await api.get(url, { responseType: "blob" });
      const cd = r.headers["content-disposition"] || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const href = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = href; a.download = m ? m[1] : fallbackName; a.click();
      URL.revokeObjectURL(href);
    } catch (e) { toast.error(apiErr(e)); }
  };

  const previewItem = async (it) => {
    try {
      const r = await api.get(`/claims/${selected.id}/items/${it.id}/download`, { responseType: "blob" });
      const fn = (it.filename || "").toLowerCase();
      const isPdf = fn.endsWith(".pdf");
      const isImg = /\.(png|jpe?g|webp)$/.test(fn);
      const blob = new Blob([r.data], { type: isPdf ? "application/pdf" : (isImg ? "image/*" : "application/octet-stream") });
      const url = URL.createObjectURL(blob);
      if (isPdf || isImg) setPreview({ label: it.filename, kind: isPdf ? "pdf" : "img", url });
      else { authedDownload(`/claims/${selected.id}/items/${it.id}/download`, it.filename); URL.revokeObjectURL(url); }
    } catch (e) { toast.error(apiErr(e)); }
  };
  const closePreview = () => { if (preview?.url) URL.revokeObjectURL(preview.url); setPreview(null); };

  const pollJob = async (cid, jobId) => {
    for (let i = 0; i < 150; i++) {
      await new Promise((res) => setTimeout(res, 2000));
      const r = await api.get(`/claims/${cid}/jobs/${jobId}`);
      if (r.data.ready) return;
      if (r.data.status === "error") throw new Error(r.data.error || "error");
    }
    throw new Error("timeout");
  };

  const downloadMerged = async () => {
    const cid = selected.id;
    if (selected.validation?.status === "blocked") {
      toast.error(t("blockedCannotFinalize"));
      return;
    }
    api.post(`/claims/${cid}/to-folder`).then(() => {}).catch(() => {});
    const items = selected.items || [];
    const totalBytes = items.reduce((s, it) => s + (Number(it.size) || 0), 0);
    const isLarge = items.length > 8 || totalBytes > 15 * 1024 * 1024;
    if (!isLarge) {
      await authedDownload(`/claims/${cid}/merged`, "claim_packet.pdf");
      setTimeout(() => refreshSelected(cid), 800);
      return;
    }
    setPacketBuilding(true);
    const tid = toast.loading(t("generatingPacket"));
    try {
      const r = await api.post(`/claims/${cid}/merged/async`);
      await pollJob(cid, r.data.job_id);
      await authedDownload(`/claims/${cid}/jobs/${r.data.job_id}/download`, "claim_packet.pdf");
      toast.dismiss(tid);
      refreshSelected(cid);
    } catch (e) {
      toast.dismiss(tid);
      toast.error(t("packetFailed"));
    } finally { setPacketBuilding(false); }
  };

  const saveRename = async (e) => {
    e.preventDefault();
    try {
      const r = await api.put(`/claims/${selected.id}/items/${renameItem.id}`, { filename: renameItem.filename, category: renameItem.category || "" });
      setSelected(r.data); setRenameItem(null); toast.success(t("saved"));
    } catch (err) { toast.error(apiErr(err)); }
  };

  const moveItemToFolder = async (it) => {
    try {
      const r = await api.post(`/claims/${selected.id}/items/${it.id}/to-folder`);
      toast.success(`${t("savedToFolder")} · ${r.data.subfolder}`);
    } catch (e) { toast.error(apiErr(e)); }
  };

  const reorderItem = async (idx, dir) => {
    const all = selected.items || [];
    const covers = all.filter((x) => x.category === "cover_sheet");
    const items = all.filter((x) => x.category !== "cover_sheet");
    const j = idx + dir;
    if (j < 0 || j >= items.length) return;
    [items[idx], items[j]] = [items[j], items[idx]];
    setSelected({ ...selected, items: [...covers, ...items] });
    try { await api.put(`/claims/${selected.id}/items-order`, { ids: [...covers, ...items].map((x) => x.id) }); }
    catch (e) { toast.error(apiErr(e)); refreshSelected(selected.id); }
  };

  const sendPacket = async (e) => {
    e.preventDefault();
    setSendBusy(true);
    try {
      await api.post(`/claims/${selected.id}/send-email`, { to: sendTo });
      toast.success(`${t("sentTo")} ${sendTo}`);
      setSendOpen(false); refreshSelected(selected.id);
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSendBusy(false); }
  };

  const statusTone = (s) => (s === "complete" ? "green" : s === "submitted" ? "tan" : "amber");
  const statusLabel = (p) => (p.status === "complete" && !p.approved ? t("legacyComplete") : t(p.status));
  const approvePacket = async () => {
    try {
      const r = await api.post(`/claims/${selected.id}/approve`);
      setSelected(r.data); toast.success(t("packetApprovedToast")); load();
    } catch (err) { toast.error(apiErr(err)); }
  };
  const setTracking = async (field, value) => {
    try {
      const r = await api.put(`/claims/${selected.id}/tracking`, { [field]: value });
      setSelected(r.data); toast.success(t("trackingSaved"));
    } catch (err) { toast.error(apiErr(err)); }
  };

  // ---------- Detail view ----------
  if (selected) {
    const allItems = selected.items || [];
    const cover = allItems.find((x) => x.category === "cover_sheet");
    const items = allItems.filter((x) => x.category !== "cover_sheet");
    const frozen = selected.approved || selected.submission_status === "submitted" || selected.status === "complete";
    return (
      <div data-testid="claim-detail">
        <PageHeader title={selected.name}
          subtitle={`${selected.claim_number ? fmtDate(selected.claim_number) : t("claimNo") + " —"} · ${allItems.length} ${t("items")}`}
          action={
            <div className="flex flex-wrap gap-2">
              <Btn variant="outline" onClick={() => { setSelected(null); load(); }} data-testid="claim-back"><ChevronLeft className="w-4 h-4" />{t("backToPackets")}</Btn>
              <Btn variant="outline" onClick={() => openEdit(selected)} data-testid="claim-edit-detail"><Pencil className="w-4 h-4" />{t("edit")}</Btn>
              <Btn variant="outline" onClick={() => { setSendTo(""); setSendOpen(true); }} data-testid="claim-send"><Send className="w-4 h-4" />{t("send")}</Btn>
              {!selected.approved && (
                <Btn variant="outline" onClick={approvePacket} data-testid="claim-approve-btn"
                  disabled={selected.validation?.status === "blocked" || (selected.approval_blockers || []).length > 0}
                  title={(selected.approval_blockers || []).join(" ") || (selected.validation?.status === "blocked" ? t("blockedCannotFinalize") : undefined)}>
                  <CheckCircle2 className="w-4 h-4" />{t("approvePacket")}
                </Btn>
              )}
              <Btn onClick={downloadMerged} disabled={packetBuilding || selected.validation?.status === "blocked"} data-testid="claim-download-merged"
                title={selected.validation?.status === "blocked" ? t("blockedCannotFinalize") : undefined}>
                {packetBuilding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                {packetBuilding ? t("generatingPacket") : t("mergeSavePdf")}
              </Btn>
            </div>} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("patient")}</p>
            <p className="mt-1 text-moneygreen-800 font-semibold">{selected.patient_name || "—"}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("packetStatus")}</p>
            <div className="mt-1 flex flex-wrap gap-2"><Badge tone={statusTone(selected.status)} data-testid="claim-status-badge">{statusLabel(selected)}</Badge>
              {selected.ready_to_approve && <Badge tone="green" data-testid="claim-ready-badge"><CheckCircle2 className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />{t("readyToApprove")}</Badge>}</div>
          </Card>
          <Card className="p-4 lg:col-span-3" data-testid="claim-required-docs-card">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500 mb-2">{t("requiredDocuments")}</p>
            <div className="flex flex-wrap gap-2">
              {[["cover_sheet", "reqCoverSheet"], ["va_disability_letter", "reqDisabilityLetter"], ["invoice", "reqInvoice"], ["progress_note", "reqProgressNote"],
                ["provider_exequatur", "reqExequatur"], ["provider_diploma", "reqDiploma"]].map(([cat, key]) => {
                const ok = (selected.items || []).some((x) => x.category === cat);
                return <Badge key={cat} tone={ok ? "green" : "red"} data-testid={`required-doc-${cat}`}>{ok ? "✓" : "✗"} {t(key)}</Badge>;
              })}
            </div>
            {!selected.approved && (selected.approval_blockers || []).length > 0 && (
              <ul className="mt-3 text-sm text-red-700 list-disc pl-5" data-testid="claim-approval-blockers">
                {selected.approval_blockers.map((b) => <li key={b}>{b}</li>)}
              </ul>
            )}
          </Card>
          <Card className="p-4 lg:col-span-3" data-testid="claim-tracking-card">
            <div className="flex flex-wrap gap-6 items-end text-sm">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("approvalStatus")}</p>
                <p className="mt-1 text-stone-700" data-testid="claim-approval-info">
                  {selected.approved ? `${t("approvedLabel")} · ${t("approvedByLabel")} ${selected.approved_by || "—"} · ${fmtDate((selected.approved_at || "").slice(0, 10))}`
                    : selected.status === "complete" ? t("legacyComplete") : t("notApproved")}
                </p>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("submissionStatus")}</p>
                <select value={selected.submission_status || "not_submitted"} onChange={(e) => setTracking("submission_status", e.target.value)}
                  className={inputCls + " mt-1 !w-auto"} data-testid="claim-submission-select">
                  <option value="not_submitted">{t("notSubmitted")}</option><option value="submitted">{t("submitted")}</option>
                </select>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("paymentStatus")}</p>
                <select value={selected.payment_status || "unpaid"} onChange={(e) => setTracking("payment_status", e.target.value)}
                  className={inputCls + " mt-1 !w-auto"} data-testid="claim-payment-select">
                  <option value="unpaid">{t("unpaid")}</option><option value="paid">{t("paid")}</option><option value="denied">{t("denied")}</option>
                </select>
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("createdBy")}</p>
            <p className="mt-1 text-stone-600 text-sm">{selected.created_by || "—"}</p>
          </Card>
        </div>
        {selected.validation && <ClaimValidation v={selected.validation} t={t} onFix={fixClaimDate} fixing={fixing} />}
        {selected.invoice_summary && (
          <Card className="p-4 mb-5" data-testid="claim-invoice-summary">
            <p className="text-xs font-bold uppercase tracking-wider text-stone-500 mb-3">{t("claimSummary")}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-stone-500">{t("invoiceNumber")}</p>
                <p className="mt-1 font-mono font-bold text-moneygreen-800" data-testid="claim-summary-invoice-number">
                  {selected.invoice_summary.invoice_number || "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-stone-500">{t("amountBilled")}</p>
                <p className="mt-1 font-bold text-moneygreen-800" data-testid="claim-summary-amount-billed">
                  {selected.invoice_summary.amount_billed == null ? "—" : `$${Number(selected.invoice_summary.amount_billed).toFixed(2)}`}
                </p>
              </div>
            </div>
          </Card>
        )}
        {selected.notes && <Card className="p-4 mb-5"><p className="text-sm text-stone-600 whitespace-pre-wrap">{selected.notes}</p></Card>}

        {/* Add-to-packet toolbar */}
        <Card className="p-4 mb-5">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("attachExistingForm")}</label>
              <div className="flex gap-2 mt-1.5">
                <ManagedSelect listKey="claim-forms" value={pickForm} onChange={(e) => setPickForm(e.target.value)} className={inputCls} data-testid="claim-pick-form">
                  <option value="">{t("selectForm")}</option>
                  {forms.map((f) => <option key={f.id} value={f.id}>{f.title} · {f.patient_name}</option>)}
                </ManagedSelect>
                <Btn variant="outline" onClick={attachForm} disabled={!pickForm} data-testid="claim-attach-form" className="!px-3"><Plus className="w-4 h-4" /></Btn>
              </div>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("attachInvoice")}</label>
              <div className="flex gap-2 mt-1.5">
                <ManagedSelect listKey="claim-invoices" value={pickInvoice || selected.invoice_summary?.invoice_id || ""} onChange={(e) => setPickInvoice(e.target.value)} className={inputCls} data-testid="claim-pick-invoice">
                  <option value="">{t("selectInvoice")}</option>
                  {selected.invoice_summary && !invoices.some((i) => i.id === selected.invoice_summary.invoice_id) && (
                    <option value={selected.invoice_summary.invoice_id}>
                      {selected.invoice_summary.invoice_number} · ${Number(selected.invoice_summary.amount_billed || 0).toFixed(2)}
                    </option>
                  )}
                  {invoices.map((i) => <option key={i.id} value={i.id}>{i.invoice_number} · {i.patient_name} · ${i.total}</option>)}
                </ManagedSelect>
                <Btn variant="outline" onClick={attachInvoice} disabled={!pickInvoice} data-testid="claim-attach-invoice" className="!px-3"><Plus className="w-4 h-4" /></Btn>
              </div>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("attachNote")}</label>
              <div className="flex gap-2 mt-1.5">
                <ManagedSelect listKey="claim-notes" value={pickNote} onChange={(e) => setPickNote(e.target.value)} className={inputCls} data-testid="claim-pick-note">
                  <option value="">{t("selectNote")}</option>
                  {notes.map((n) => <option key={n.id} value={n.id}>{n.patient_name} · {fmtDate(n.date)}{n.reason ? ` · ${n.reason}` : ""}</option>)}
                </ManagedSelect>
                <Btn variant="outline" onClick={attachNote} disabled={!pickNote} data-testid="claim-attach-note" className="!px-3"><Plus className="w-4 h-4" /></Btn>
              </div>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("uploadDocument")}</label>
              <div className="mt-1.5">
                <input ref={fileRef} type="file" onChange={onUpload} data-testid="claim-upload-input"
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.txt,.xls,.xlsx"
                  className="block w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer disabled:opacity-60"
                  disabled={busy} />
              </div>
            </div>
          </div>
          <p className="text-xs text-stone-400 mt-3">{t("mergeHint")}</p>
        </Card>

        {/* Items list */}
        <Card className="overflow-hidden">
          {(
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                    <th className="px-5 py-3">{t("itemSource")}</th>
                    <th className="px-5 py-3">{t("filename")}</th>
                    <th className="px-5 py-3 text-right">{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-border/60 bg-moneygreen-50/40" data-testid="claim-item-cover-sheet">
                    <td className="px-5 py-3"><Badge tone={cover ? "green" : "red"}>{t("coverSheetLabel")}</Badge></td>
                    <td className="px-5 py-3 text-stone-700">
                      <span className="font-semibold">{t("coverSheetFixed")}</span>
                      <span className="block text-xs text-stone-500" data-testid="claim-cover-sheet-file">{cover ? cover.filename : t("notUploaded")}</span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end items-center gap-1">
                        <span className="text-xs text-stone-400 mr-2">{t("fixedFirst")}</span>
                        {cover && <Btn variant="ghost" onClick={() => previewItem(cover)} data-testid="claim-cover-sheet-view" className="!px-2" title={t("view")}><Eye className="w-4 h-4" /></Btn>}
                        {cover && !frozen && <Btn variant="ghost" onClick={() => removeItem(cover.id)} disabled={!!deleting} data-testid="claim-cover-sheet-remove" className="!px-2 !text-destructive" title={t("removeFromPacket")}><Trash2 className="w-4 h-4" /></Btn>}
                        {!frozen && (
                          <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold cursor-pointer bg-moneygreen-600 text-white hover:bg-moneygreen-700 transition-colors ${busy ? "opacity-60 pointer-events-none" : ""}`} data-testid="claim-cover-sheet-upload-btn">
                            <Upload className="w-3.5 h-3.5" />{cover ? t("replace") : t("uploadCoverSheet")}
                            <input type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(e) => onUpload(e, "cover_sheet")} data-testid="claim-cover-sheet-input" />
                          </label>
                        )}
                      </div>
                    </td>
                  </tr>
                  {items.map((it, i) => {
                    const Icon = sourceIcon[it.source] || FileText;
                    return (
                      <motion.tr key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                        data-testid={`claim-item-${it.id}`}
                        className={`border-b border-border/60 ${i % 2 ? "bg-tan-50/40" : ""}`}>
                        <td className="px-5 py-3"><Badge tone={it.category ? "green" : (sourceTone[it.source] || "gray")} data-testid={`claim-item-type-${it.id}`}>{it.category ? t(categoryLabelKey[it.category] || `src_${it.source}`) : t(`src_${it.source}`)}</Badge></td>
                        <td className="px-5 py-3 text-stone-700"><span className="inline-flex items-center gap-2"><Icon className="w-4 h-4 text-stone-400" />{it.filename}</span></td>
                        <td className="px-5 py-3">
                          <div className="flex justify-end items-center gap-1">
                            <div className="flex flex-col mr-1">
                              <button onClick={() => reorderItem(i, -1)} disabled={i === 0} data-testid={`claim-item-up-${it.id}`} className="text-stone-400 hover:text-moneygreen-600 disabled:opacity-30" title={t("moveUp")}><ArrowUp className="w-3.5 h-3.5" /></button>
                              <button onClick={() => reorderItem(i, 1)} disabled={i === items.length - 1} data-testid={`claim-item-down-${it.id}`} className="text-stone-400 hover:text-moneygreen-600 disabled:opacity-30" title={t("moveDown")}><ArrowDown className="w-3.5 h-3.5" /></button>
                            </div>
                            <Btn variant="ghost" onClick={() => previewItem(it)} data-testid={`claim-item-view-${it.id}`} className="!px-2" title={t("view")}><Eye className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => setRenameItem({ id: it.id, filename: it.filename, category: it.category || "" })} data-testid={`claim-item-edit-${it.id}`} className="!px-2" title={t("edit")}><Pencil className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => moveItemToFolder(it)} data-testid={`claim-item-move-${it.id}`} className="!px-2 !text-moneygreen-700" title={t("moveToFolderTitle")}><FolderInput className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => authedDownload(`/claims/${selected.id}/items/${it.id}/download`, it.filename)} data-testid={`claim-item-download-${it.id}`} className="!px-2" title={t("saveAsPdf")}><Download className="w-4 h-4" /></Btn>
                            <Btn variant="ghost" onClick={() => removeItem(it.id)} disabled={!!deleting}
                              data-testid={`claim-item-remove-${it.id}`} className="!px-2 !text-destructive" title={t("removeFromPacket")}>
                              {deleting === `item:${it.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                            </Btn>
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <PacketModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing}
          form={form} set={set} save={save} patients={patients} t={t}
          setClaimPatient={setClaimPatient} setClaimDate={setClaimDate} />

        <Modal open={!!preview} onClose={closePreview} title={preview?.label || t("preview")} wide>
          {preview && (
            <div className="rounded-lg overflow-hidden border border-border bg-stone-50">
              {preview.kind === "img"
                ? <img src={preview.url} alt={preview.label} className="max-h-[70vh] w-auto mx-auto" />
                : <iframe title={preview.label} src={preview.url} className="w-full h-[70vh]" />}
            </div>
          )}
        </Modal>

        <Modal open={!!renameItem} onClose={() => setRenameItem(null)} title={t("rename")}>
          {renameItem && (
            <form onSubmit={saveRename} className="space-y-4">
              <Field label={t("filename")}>
                <input required value={renameItem.filename} onChange={(e) => setRenameItem({ ...renameItem, filename: e.target.value })} className={inputCls} data-testid="claim-item-rename-input" />
              </Field>
              <Field label={t("documentCategory")}>
                <select value={renameItem.category} onChange={(e) => setRenameItem({ ...renameItem, category: e.target.value })} className={inputCls} data-testid="claim-item-category">
                  <option value="">{t("catNone")}</option>
                  <option value="cover_sheet">{t("catCoverSheet")}</option>
                  <option value="invoice">{t("catInvoice")}</option>
                  <option value="progress_note">{t("catProgressNote")}</option>
                  <option value="va_disability_letter">{t("catVaLetter")}</option>
                  <option value="fmp_registration">{t("catFmpRegistration")}</option>
                  <option value="provider_exequatur">{t("catExequatur")}</option>
                  <option value="provider_diploma">{t("catDiploma")}</option>
                </select>
              </Field>
              <p className="text-xs text-stone-400">{t("categoryHint")}</p>
              <div className="flex justify-end gap-2 pt-2">
                <Btn variant="outline" type="button" onClick={() => setRenameItem(null)}>{t("cancel")}</Btn>
                <Btn type="submit" data-testid="claim-item-rename-save">{t("save")}</Btn>
              </div>
            </form>
          )}
        </Modal>

        <Modal open={sendOpen} onClose={() => setSendOpen(false)} title={t("sendMergedPacket")}>
          <form onSubmit={sendPacket} className="space-y-4">
            <p className="text-sm text-stone-500">{t("sendPacketHint")}</p>
            <Field label={t("recipientEmail")}>
              <input type="email" required value={sendTo} onChange={(e) => setSendTo(e.target.value)} className={inputCls} data-testid="claim-send-input" placeholder="recipient@email.com" />
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setSendOpen(false)}>{t("cancel")}</Btn>
              <Btn type="submit" disabled={sendBusy || !sendTo} data-testid="claim-send-submit"><Send className="w-4 h-4" />{t("send")}</Btn>
            </div>
          </form>
        </Modal>
      </div>
    );
  }

  // ---------- List view ----------
  return (
    <div data-testid="claims-page">
      <PageHeader title={t("claims")} subtitle={t("claimsSubtitle")}
        action={
          <div className="flex flex-wrap gap-2">
            <Btn variant="outline" onClick={() => { setFromDateOpen(true); setFromDate({ patient_id: "", date: "" }); setDatePatients([]); }} data-testid="build-from-date-btn"><CalendarClock className="w-4 h-4" />{t("buildFromDate")}</Btn>
            <Btn onClick={openNew} data-testid="new-claim-btn"><FilePlus className="w-4 h-4" />{t("newClaim")}</Btn>
          </div>} />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b border-border bg-tan-50/40" data-testid="claim-check-filter">
          <span className="text-xs font-bold uppercase tracking-wider text-stone-500 mr-1">{t("filterByCheck")}</span>
          {[
            { key: "all", label: t("filterAll"), count: packets.length, cls: "data-[on=true]:bg-stone-700 data-[on=true]:text-white border-stone-300" },
            { key: "blocked", label: t("chipBlocked"), count: checkCounts.blocked || 0, cls: "data-[on=true]:bg-red-600 data-[on=true]:text-white data-[on=true]:border-red-600 border-red-200 text-red-700" },
            { key: "review", label: t("chipReview"), count: checkCounts.review || 0, cls: "data-[on=true]:bg-amber-500 data-[on=true]:text-white data-[on=true]:border-amber-500 border-amber-200 text-amber-700" },
            { key: "ready", label: t("chipReady"), count: checkCounts.ready || 0, cls: "data-[on=true]:bg-moneygreen-600 data-[on=true]:text-white data-[on=true]:border-moneygreen-600 border-moneygreen-200 text-moneygreen-700" },
            { key: "approvable", label: t("readyToApprove"), count: packets.filter((p) => p.ready_to_approve).length, cls: "data-[on=true]:bg-moneygreen-800 data-[on=true]:text-white data-[on=true]:border-moneygreen-800 border-moneygreen-300 text-moneygreen-800" },
          ].map((f) => (
            <button key={f.key} data-on={checkFilter === f.key} onClick={() => { setCheckFilter(f.key); setBulkSel([]); }}
              data-testid={`claim-filter-${f.key}`}
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-semibold transition-colors ${f.cls}`}>
              {f.label}<span className="opacity-70">· {f.count}</span>
            </button>
          ))}
        </div>
        {checkFilter === "approvable" && (
          <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-border bg-moneygreen-50/50" data-testid="bulk-approve-bar">
            <label className="inline-flex items-center gap-2 text-sm text-stone-700 cursor-pointer">
              <input type="checkbox" data-testid="bulk-select-all" disabled={!eligibleVisible.length}
                checked={eligibleVisible.length > 0 && eligibleVisible.every((p) => bulkSel.includes(p.id))}
                onChange={(e) => setBulkSel(e.target.checked ? eligibleVisible.map((p) => p.id) : [])} />
              {t("selectAll")}
            </label>
            <Btn onClick={() => setBulkOpen(true)} disabled={!bulkSel.length} data-testid="bulk-approve-btn">
              <CheckCircle2 className="w-4 h-4" />{t("approveSelected")} ({bulkSel.length})
            </Btn>
            <span className="text-xs text-stone-500">{t("bulkApproveHint")}</span>
          </div>
        )}
        {visiblePackets.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-5 py-3">{t("claimName")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("patient")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("claimNo")}</th>
                  <th className="px-5 py-3">{t("items")}</th>
                  <th className="px-5 py-3">{t("packetStatus")}</th>
                  <th className="px-5 py-3 hidden sm:table-cell">{t("validationColumn")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {visiblePackets.map((p, i) => (
                  <motion.tr key={p.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`claim-row-${p.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 cursor-pointer ${p.status === "complete" ? "bg-moneygreen-50" : (i % 2 ? "bg-tan-50/40" : "")}`}
                    onClick={() => refreshSelected(p.id)}>
                    <td className="px-5 py-3">
                      {checkFilter === "approvable" && (
                        <span className="inline-flex mr-2 align-middle" onClick={(e) => e.stopPropagation()}>
                          {bulkEligible(p)
                            ? <input type="checkbox" checked={bulkSel.includes(p.id)} onChange={() => toggleBulk(p.id)} data-testid={`bulk-select-${p.id}`} />
                            : <span className="text-[11px] text-amber-700" data-testid={`bulk-individual-${p.id}`} title={t("approveIndividuallyHint")}>{t("approveIndividually")}</span>}
                        </span>
                      )}
                      <span className="inline-flex items-center gap-2 font-semibold text-moneygreen-800"><FolderArchive className={`w-4 h-4 ${p.status === "complete" ? "text-moneygreen-600" : "text-moneygreen-500"}`} />{p.name}</span>
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{p.patient_name || "—"}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-500 font-mono text-xs">{fmtDate(p.claim_number) || "—"}</td>
                    <td className="px-5 py-3 text-stone-600">{(p.items || []).length}</td>
                    <td className="px-5 py-3"><div className="flex flex-wrap gap-1.5"><Badge tone={statusTone(p.status)}>{statusLabel(p)}</Badge>
                      {p.ready_to_approve && <Badge tone="green" data-testid={`claim-ready-badge-${p.id}`}><CheckCircle2 className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />{t("readyToApprove")}</Badge>}</div></td>
                    <td className="px-5 py-3 hidden sm:table-cell"><ValChip v={p.validation} t={t} /></td>
                    <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <Btn variant="outline" onClick={() => refreshSelected(p.id)} data-testid={`claim-open-${p.id}`}>{t("view")}</Btn>
                        <Btn variant="ghost" onClick={() => openEdit(p)} data-testid={`claim-edit-${p.id}`} className="!px-2"><Pencil className="w-4 h-4" /></Btn>
                        <Btn variant="ghost" onClick={() => remove(p.id)} disabled={!!deleting}
                          data-testid={`claim-delete-${p.id}`} className="!px-2 !text-destructive">
                          {deleting === `claim:${p.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        </Btn>
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <PacketModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing}
        form={form} set={set} save={save} patients={patients} t={t}
        setClaimPatient={setClaimPatient} setClaimDate={setClaimDate} />

      <Modal open={fromDateOpen} onClose={closeFromDate} title={t("buildFromDateTitle")}>
        <form onSubmit={buildFromDate} className="space-y-4">
          <p className="text-sm text-stone-500">{t("buildFromDateHint")}</p>
          <Field label={t("serviceDate")}>
            <input required type="date" value={fromDate.date} onChange={pickFromDateDate} className={inputCls} data-testid="fd-date" />
          </Field>
          <Field label={t("patient")}>
            <ManagedSelect listKey="patients" required disabled={!fromDate.date || datePatientsLoading}
              value={fromDate.patient_id} onChange={(e) => setFromDate((f) => ({ ...f, patient_id: e.target.value }))}
              className={inputCls} data-testid="fd-patient">
              <option value="">
                {!fromDate.date ? t("selectDateFirst") : datePatientsLoading ? t("loading") : datePatients.length === 0 ? t("noCompletedVisitsOnDate") : t("selectPatient")}
              </option>
              {datePatients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </ManagedSelect>
            {fromDate.date && !datePatientsLoading && datePatients.length === 0 && (
              <p className="text-xs text-stone-500 mt-1.5">{t("noCompletedVisitsOnDateHint")}</p>
            )}
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={closeFromDate}>{t("cancel")}</Btn>
            <Btn type="submit" disabled={building || !fromDate.patient_id || !fromDate.date} data-testid="fd-build-btn">{t("build")}</Btn>
          </div>
        </form>
      </Modal>
      <Modal open={bulkOpen} onClose={() => !bulkBusy && setBulkOpen(false)} title={t("bulkConfirmTitle")}>
        <p className="text-sm text-stone-600 mb-3">{t("bulkConfirmText")}</p>
        <ul className="text-sm text-stone-700 list-disc pl-5 max-h-60 overflow-y-auto mb-4" data-testid="bulk-confirm-list">
          {packets.filter((p) => bulkSel.includes(p.id)).map((p) => <li key={p.id}>{p.name}</li>)}
        </ul>
        <div className="flex justify-end gap-2">
          <Btn variant="outline" onClick={() => setBulkOpen(false)} disabled={bulkBusy} data-testid="bulk-confirm-cancel">{t("cancel")}</Btn>
          <Btn onClick={async () => { await runBulkApprove(); setBulkOpen(false); }} disabled={bulkBusy} data-testid="bulk-confirm-submit">
            {bulkBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}{t("approveSelected")} ({bulkSel.length})
          </Btn>
        </div>
      </Modal>
      <Modal open={!!bulkResult} onClose={() => setBulkResult(null)} title={t("bulkResultTitle")}>
        {bulkResult && (
          <div className="space-y-3 text-sm" data-testid="bulk-result">
            <p className="font-semibold text-moneygreen-800" data-testid="bulk-result-approved">{t("approvedLabel")}: {bulkResult.approved.length}</p>
            <ul className="list-disc pl-5 text-stone-700">{bulkResult.approved.map((a) => <li key={a.id}>{a.name}</li>)}</ul>
            {bulkResult.skipped.length > 0 && (
              <>
                <p className="font-semibold text-amber-700" data-testid="bulk-result-skipped">{t("bulkSkipped")}: {bulkResult.skipped.length}</p>
                <ul className="list-disc pl-5 text-stone-700">{bulkResult.skipped.map((s) => <li key={s.id}><b>{s.name}</b> — {s.reason}</li>)}</ul>
              </>
            )}
            <div className="flex justify-end"><Btn onClick={() => setBulkResult(null)} data-testid="bulk-result-close">OK</Btn></div>
          </div>
        )}
      </Modal>

    </div>
  );
}

function PacketModal({ open, onClose, editing, form, set, save, patients, t, setClaimPatient, setClaimDate }) {
  return (
    <Modal open={open} onClose={onClose} title={editing ? t("editClaim") : t("newClaim")}>
      <form onSubmit={save} className="space-y-4">
        <Field label={t("patient")}>
          <ManagedSelect listKey="patients" value={form.patient_id} onChange={setClaimPatient} className={inputCls} data-testid="cf-patient">
            <option value="">{t("selectPatient")}</option>
            {patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </ManagedSelect>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("claimNo")}><input type="date" value={form.claim_number} onChange={setClaimDate} className={inputCls} data-testid="cf-number" /></Field>
          <Field label={t("packetStatus")}>
            <select value={form.status} onChange={set("status")} className={inputCls} data-testid="cf-status">
              <option value="draft">{t("draft")}</option>
              <option value="submitted">{t("submitted")}</option>
              {form.status === "complete" && <option value="complete">{t("complete")}</option>}
            </select>
          </Field>
        </div>
        <Field label={t("claimName")}><input required value={form.name} onChange={set("name")} className={inputCls} data-testid="cf-name" /></Field>
        <div className="pt-2 mt-1 border-t border-border">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500 mb-2 mt-2">{t("fmpCoverDetails")}</p>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("vaClaimNumber")}><input value={form.va_claim_number} onChange={set("va_claim_number")} className={inputCls} data-testid="cf-va-number" /></Field>
            <Field label={t("paymentTo")}>
              <select value={form.payment_to} onChange={set("payment_to")} className={inputCls} data-testid="cf-payment-to">
                <option value="provider">{t("payProvider")}</option>
                <option value="veteran">{t("payVeteran")}</option>
              </select>
            </Field>
          </div>
          <Field label={t("veteranPhysicalAddress")}><input value={form.veteran_physical_address} onChange={set("veteran_physical_address")} className={inputCls} data-testid="cf-vet-physical" /></Field>
          <Field label={t("veteranMailingAddress")}><input value={form.veteran_mailing_address} onChange={set("veteran_mailing_address")} className={inputCls} data-testid="cf-vet-mailing" /></Field>
          <Field label={t("diagnosisNarrative")}><textarea rows={2} value={form.diagnosis_narrative} onChange={set("diagnosis_narrative")} className={inputCls} data-testid="cf-diagnosis" /></Field>
        </div>
        <Field label={t("extraNotes")}><textarea rows={3} value={form.notes} onChange={set("notes")} className={inputCls} data-testid="cf-notes" /></Field>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="outline" type="button" onClick={onClose}>{t("cancel")}</Btn>
          <Btn type="submit" data-testid="save-claim-btn">{t("save")}</Btn>
        </div>
      </form>
    </Modal>
  );
}
