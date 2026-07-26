import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { Private } from "../context/PrivacyContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { ManagedSelect } from "../components/ManagedSelect";
import { fmtDate } from "../lib/date";
import {
  DollarSign, UploadCloud, FileText, Wand2, CheckCircle2, AlertTriangle, XCircle,
  Download, Eye, RefreshCw, CalendarClock, ChevronLeft,
} from "lucide-react";
import { toast } from "sonner";

const statusMeta = {
  ready: { tone: "green", Icon: CheckCircle2, key: "validationReady" },
  review: { tone: "amber", Icon: AlertTriangle, key: "validationReview" },
  blocked: { tone: "red", Icon: XCircle, key: "validationBlocked" },
};

export default function ClaimBuilder() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [patientId, setPatientId] = useState("");
  const [template, setTemplate] = useState(null);
  const [versions, setVersions] = useState(0);
  const [visits, setVisits] = useState([]);
  const [visit, setVisit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [packet, setPacket] = useState(null);
  const [coverConfirmed, setCoverConfirmed] = useState(false);
  const [dateModal, setDateModal] = useState(false);
  const [dayFiles, setDayFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [dateEdit, setDateEdit] = useState("");
  const fileRef = useRef(null);

  useEffect(() => {
    api.get("/claims/options/patients").then((r) => setPatients(r.data)).catch((err) => console.error(err));
  }, []);

  useEffect(() => {
    if (!visit) { setDayFiles([]); setSelectedFiles([]); return; }
    setDateEdit(visit.date || "");
    api.get(`/fmp/day-files/${patientId}?date=${visit.date || ""}`)
      .then((r) => setDayFiles(r.data || [])).catch(() => setDayFiles([]));
  }, [visit, patientId]);

  const loadPatient = useCallback(async (pid) => {
    setTemplate(null); setVisits([]); setVisit(null); setPacket(null); setDayFiles([]); setSelectedFiles([]);
    if (!pid) return;
    try {
      const tr = await api.get(`/fmp/templates/${pid}`);
      setTemplate(tr.data.template); setVersions(tr.data.versions || 0);
    } catch (e) { toast.error(apiErr(e)); }
    try { setVisits((await api.get(`/fmp/visits/${pid}`)).data); } catch (e) { toast.error(apiErr(e)); }
  }, []);

  const onPatient = (e) => { const v = e.target.value; setPatientId(v); loadPatient(v); };

  const uploadTemplate = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) { toast.error("PDF only"); return; }
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      await api.post(`/fmp/templates/${patientId}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(t("uploadTemplate") + " ✓");
      await loadPatient(patientId);
    } catch (e) { toast.error(apiErr(e)); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const toggleFile = (id) =>
    setSelectedFiles((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const generateWith = async (manualDate) => {
    if (!visit) return;
    setBusy(true); setPacket(null); setCoverConfirmed(false);
    try {
      const r = await api.post("/fmp/generate", {
        patient_id: patientId, note_id: visit.note_id,
        invoice_id: (packet && packet.source_invoice_id) || visit.invoice_id || null,
        manual_date: manualDate || null, attachment_item_ids: selectedFiles,
      });
      setPacket(r.data);
      setDateEdit(r.data.claim_number || manualDate || visit.date || "");
      if (r.data.duplicate_of) toast.warning(t("dupWarning"));
    } catch (e) { toast.error(apiErr(e)); }
    finally { setBusy(false); }
  };
  const generate = () => generateWith(dateEdit || null);

  const approve = async () => {
    try {
      const r = await api.post(`/fmp/claims/${packet.id}/approve`, { confirm_cover_date: coverConfirmed });
      setPacket({ ...packet, ...r.data });
      toast.success(t("approvePacket") + " ✓");
    } catch (e) { toast.error(apiErr(e)); }
  };

  const authedDownload = async () => {
    try {
      const r = await api.get(`/claims/${packet.id}/merged`, { responseType: "blob" });
      const href = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = href; a.download = (packet.name || "claim_packet").replace(/\s+/g, "_") + ".pdf"; a.click();
      URL.revokeObjectURL(href);
    } catch (e) { toast.error(apiErr(e)); }
  };

  const canGenerate = patientId && visit && template && template.date_field;
  const val = packet?.validation;
  const meta = val ? statusMeta[val.status] : null;

  return (
    <div data-testid="claim-builder-page">
      <PageHeader
        title={<span className="inline-flex items-center gap-2"><DollarSign className="w-6 h-6 text-moneygreen-600" />{t("claimBuilder")}</span>}
        subtitle={t("claimBuilderSubtitle")}
        action={<Btn variant="outline" onClick={() => navigate("/claims")} data-testid="cb-to-claims"><ChevronLeft className="w-4 h-4" />{t("claims")}</Btn>} />

      {/* Step 1: patient */}
      <Card className="p-5 mb-5">
        <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("patient")}</label>
        <ManagedSelect listKey="patients" value={patientId} onChange={onPatient} className={`${inputCls} mt-1.5 max-w-md`} data-testid="cb-patient">
          <option value="">{t("selectPatient")}</option>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </ManagedSelect>
      </Card>

      {patientId && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
          {/* Template panel */}
          <Card className="p-5">
            <h3 className="font-heading font-bold text-moneygreen-800 mb-3 flex items-center gap-2"><FileText className="w-4 h-4" />{t("coverSheetTemplate")}</h3>
            {!template ? (
              <div>
                <p className="text-sm text-stone-500 mb-3">{t("noTemplateYet")}</p>
                <input ref={fileRef} type="file" accept=".pdf" data-testid="cb-template-upload"
                  onChange={(e) => uploadTemplate(e.target.files[0])} disabled={busy}
                  className="block w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer" />
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-semibold text-moneygreen-800 truncate">{template.filename}</span>
                  <Badge tone="tan">{t("templateVersion")} {template.version}</Badge>
                </div>
                {template.date_field
                  ? <Badge tone="green" data-testid="cb-datefield-ok"><span className="inline-flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />{t("dateFieldConfigured")}</span></Badge>
                  : <Badge tone="red" data-testid="cb-datefield-missing"><span className="inline-flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" />{t("dateFieldNotSet")}</span></Badge>}
                <div className="flex flex-wrap gap-2 pt-1">
                  <Btn variant="outline" onClick={() => setDateModal(true)} data-testid="cb-set-datefield"><Wand2 className="w-4 h-4" />{t("setDateField")}</Btn>
                  <Btn variant="outline" onClick={() => fileRef.current?.click()} data-testid="cb-replace-template"><RefreshCw className="w-4 h-4" />{t("replaceTemplate")}</Btn>
                  <input ref={fileRef} type="file" accept=".pdf" className="hidden"
                    onChange={(e) => uploadTemplate(e.target.files[0])} />
                </div>
                <p className="text-xs text-stone-400">{versions} {t("templateVersionsStored")}</p>
              </div>
            )}
          </Card>

          {/* Visit panel */}
          <Card className="p-5">
            <h3 className="font-heading font-bold text-moneygreen-800 mb-3 flex items-center gap-2"><CalendarClock className="w-4 h-4" />{t("selectVisit")}</h3>
            {visits.length === 0 ? <Empty text={t("noVisits")} /> : (
              <div className="space-y-2 max-h-72 overflow-y-auto custom-scroll">
                {visits.map((v) => (
                  <button key={v.note_id} type="button" onClick={() => setVisit(v)} data-testid={`cb-visit-${v.note_id}`}
                    className={`w-full text-left p-3 rounded-md border transition-colors duration-200 ${visit?.note_id === v.note_id ? "border-moneygreen-500 bg-moneygreen-50" : "border-border hover:bg-tan-50"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-moneygreen-800">{fmtDate(v.date) || "—"}</span>
                      {v.signed ? <Badge tone="green">{t("signedBadge")}</Badge> : <Badge tone="amber">{t("unsigned")}</Badge>}
                    </div>
                    <p className="text-xs text-stone-500 mt-1">{v.provider || "—"}{v.reason ? ` · ${v.reason}` : ""}</p>
                    <p className="text-xs text-stone-400 mt-0.5">{v.invoice_number ? `${t("invoice")} ${v.invoice_number}` : t("noInvoiceLinked")}{v.icd10 ? ` · ICD-10 ${v.icd10}` : ""}</p>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Files already on file for this patient / day */}
      {visit && dayFiles.length > 0 && (
        <Card className="p-5 mb-5" data-testid="cb-dayfiles">
          <h3 className="font-heading font-bold text-moneygreen-800 mb-3 flex items-center gap-2"><FileText className="w-4 h-4" />{t("dayFilesTitle")} · {fmtDate(visit.date)}</h3>
          <div className="grid sm:grid-cols-2 gap-2">
            {dayFiles.map((f) => (
              <label key={f.id} className="flex items-center gap-2 p-2 rounded-md border border-border hover:bg-tan-50 cursor-pointer" data-testid={`cb-dayfile-${f.id}`}>
                <input type="checkbox" checked={selectedFiles.includes(f.id)} onChange={() => toggleFile(f.id)} className="w-4 h-4 accent-moneygreen-600" />
                <span className="text-sm text-stone-700 truncate">{f.filename}</span>
              </label>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-2">{t("dayFilesHint")}</p>
        </Card>
      )}

      {patientId && (
        <div className="flex justify-center mb-6">
          <Btn onClick={generate} disabled={!canGenerate || busy} data-testid="cb-generate"
            className="!px-8 !py-3 text-base">
            <Wand2 className="w-5 h-5" />{busy ? t("generating") : t("generateClaimPacket")}
          </Btn>
        </div>
      )}

      {/* Review screen */}
      {packet && (
        <Card className="p-6" data-testid="cb-review">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4 mb-4">
            <div>
              <h3 className="font-heading text-lg font-bold text-moneygreen-800">{t("claimPacketReview")}</h3>
              <p className="text-sm text-stone-500"><Private value={packet.patient_name} /> · {t("dateOfService")}: {fmtDate(packet.claim_number) || "—"} · {packet.items.length} {t("items")}</p>
            </div>
            {meta && <Badge tone={meta.tone} data-testid="cb-validation-status"><span className="inline-flex items-center gap-1"><meta.Icon className="w-4 h-4" />{t(meta.key)}</span></Badge>}
          </div>

          {/* Editable date of service */}
          <div className="flex flex-wrap items-end gap-2 mb-5">
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{t("changeDate")}</label>
              <input type="date" value={dateEdit} onChange={(e) => setDateEdit(e.target.value)} className={`${inputCls} !w-auto mt-1.5`} data-testid="cb-edit-date" />
            </div>
            <Btn variant="outline" onClick={() => generateWith(dateEdit)} disabled={busy} data-testid="cb-apply-date"><CalendarClock className="w-4 h-4" />{t("applyDate")}</Btn>
          </div>

          {/* Document table */}
          <table className="w-full text-sm mb-5">
            <thead>
              <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                <th className="py-2">{t("document")}</th>
                <th className="py-2">{t("dateOfService")}</th>
                <th className="py-2 text-right">{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {packet.items.map((it) => (
                <tr key={it.id} className="border-b border-border/60" data-testid={`cb-doc-${it.category || it.source}`}>
                  <td className="py-2 font-medium text-moneygreen-800">{it.filename}</td>
                  <td className="py-2 text-stone-600">{fmtDate(packet.claim_number) || "—"}</td>
                  <td className="py-2 text-right"><Badge tone="green"><span className="inline-flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />{t("included")}</span></Badge></td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Issues */}
          {val.issues.length > 0 && (
            <div className="space-y-2 mb-5" data-testid="cb-issues">
              {val.issues.map((iss, i) => (
                <div key={`${iss.level}-${i}-${iss.message.slice(0, 12)}`} className={`flex items-start gap-2 text-sm p-2.5 rounded-md ${iss.level === "blocked" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}>
                  {iss.level === "blocked" ? <XCircle className="w-4 h-4 mt-0.5 shrink-0" /> : <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />}
                  <span>{iss.message}</span>
                </div>
              ))}
            </div>
          )}

          {/* Cover-sheet review */}
          {packet.cover_review && (
            <Card className="p-4 mb-5 bg-tan-50/50">
              <h4 className="font-heading font-bold text-moneygreen-800 mb-2">{t("coverSheetUpdate")}</h4>
              <div className="grid grid-cols-2 gap-y-1 text-sm max-w-md">
                <span className="text-stone-500">{t("newDate")}</span><span className="font-semibold">{packet.cover_review.new_date}</span>
                <span className="text-stone-500">{t("dateSource")}</span><span className="font-semibold capitalize">{packet.cover_review.date_source || "—"}</span>
                <span className="text-stone-500">{t("otherFieldsChanged")}</span><span className="font-semibold">{t("no")}</span>
              </div>
              <label className="flex items-center gap-2 mt-3 text-sm cursor-pointer" data-testid="cb-confirm-cover">
                <input type="checkbox" checked={coverConfirmed} onChange={(e) => setCoverConfirmed(e.target.checked)} className="w-4 h-4 accent-moneygreen-600" />
                {t("confirmCoverDate")}
              </label>
            </Card>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 justify-end">
            <Btn variant="outline" onClick={authedDownload} data-testid="cb-download"><Download className="w-4 h-4" />{t("downloadPacket")}</Btn>
            <Btn onClick={approve} disabled={val.status === "blocked" || packet.approved} data-testid="cb-approve">
              <CheckCircle2 className="w-4 h-4" />{packet.approved ? t("approved") : t("approvePacket")}
            </Btn>
          </div>
          {val.status === "blocked" && <p className="text-xs text-red-600 text-right mt-2">{t("blockedApproveHint")}</p>}
        </Card>
      )}

      {template && (
        <DateFieldModal open={dateModal} onClose={() => setDateModal(false)} patientId={patientId}
          template={template} onSaved={() => { setDateModal(false); loadPatient(patientId); }} t={t} />
      )}
    </div>
  );
}

function DateFieldModal({ open, onClose, patientId, template, onSaved, t }) {
  const [imgUrl, setImgUrl] = useState(null);
  const [box, setBox] = useState(template.date_field || null);
  const [drawing, setDrawing] = useState(null);
  const [dateFormat, setDateFormat] = useState(template.date_field?.date_format || "MM/DD/YYYY");
  const [fontSize, setFontSize] = useState(template.date_field?.font_size || 12);
  const boxRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    let url;
    api.get(`/fmp/templates/${patientId}/preview.png`, { responseType: "blob" })
      .then((r) => { url = URL.createObjectURL(r.data); setImgUrl(url); })
      .catch((e) => toast.error(apiErr(e)));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [open, patientId]);

  const frac = (e) => {
    const rect = boxRef.current.getBoundingClientRect();
    return { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height };
  };
  const onDown = (e) => { const p = frac(e); setDrawing({ x0: p.x, y0: p.y, x1: p.x, y1: p.y }); };
  const onMove = (e) => { if (!drawing) return; const p = frac(e); setDrawing({ ...drawing, x1: p.x, y1: p.y }); };
  const onUp = () => {
    if (!drawing) return;
    const fx = Math.min(drawing.x0, drawing.x1), fy = Math.min(drawing.y0, drawing.y1);
    const fw = Math.abs(drawing.x1 - drawing.x0), fh = Math.abs(drawing.y1 - drawing.y0);
    setDrawing(null);
    if (fw > 0.01 && fh > 0.005) setBox({ page: 0, fx, fy, fw, fh });
  };

  const rectStyle = (b) => ({
    left: `${b.fx * 100}%`, top: `${b.fy * 100}%`, width: `${b.fw * 100}%`, height: `${b.fh * 100}%`,
  });

  const save = async () => {
    if (!box) { toast.error(t("drawDateHint")); return; }
    try {
      await api.put(`/fmp/templates/${template.id}/date-field`, {
        page: 0, fx: box.fx, fy: box.fy, fw: box.fw, fh: box.fh,
        date_format: dateFormat, font_size: Number(fontSize) || 12,
      });
      toast.success(t("saveDateField") + " ✓");
      onSaved();
    } catch (e) { toast.error(apiErr(e)); }
  };

  const live = drawing
    ? { fx: Math.min(drawing.x0, drawing.x1), fy: Math.min(drawing.y0, drawing.y1),
        fw: Math.abs(drawing.x1 - drawing.x0), fh: Math.abs(drawing.y1 - drawing.y0) }
    : box;

  return (
    <Modal open={open} onClose={onClose} title={t("drawDateBox")} wide>
      <div className="space-y-4">
        <p className="text-sm text-stone-500">{t("drawDateHint")}</p>
        <div ref={boxRef} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
          data-testid="cb-datebox-canvas"
          className="relative border border-border rounded-md overflow-hidden cursor-crosshair select-none bg-stone-100" style={{ userSelect: "none" }}>
          {imgUrl ? <img src={imgUrl} alt="template" draggable={false} className="w-full block pointer-events-none" />
            : <div className="h-96 flex items-center justify-center text-stone-400">…</div>}
          {live && live.fw > 0 && (
            <div className="absolute border-2 border-moneygreen-600 bg-moneygreen-500/20 pointer-events-none" style={rectStyle(live)} />
          )}
        </div>
        <div className="flex flex-wrap gap-4 items-end">
          <Field label={t("dateFormat")}>
            <select value={dateFormat} onChange={(e) => setDateFormat(e.target.value)} className={inputCls} data-testid="cb-dateformat">
              <option value="MM/DD/YYYY">MM/DD/YYYY</option>
              <option value="DD/MM/YYYY">DD/MM/YYYY</option>
              <option value="YYYY-MM-DD">YYYY-MM-DD</option>
            </select>
          </Field>
          <Field label={t("fontSize")}>
            <input type="number" min="6" max="40" value={fontSize} onChange={(e) => setFontSize(e.target.value)} className={`${inputCls} w-24`} data-testid="cb-fontsize" />
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="outline" onClick={onClose}>{t("cancel")}</Btn>
          <Btn onClick={save} disabled={!box} data-testid="cb-save-datefield"><CheckCircle2 className="w-4 h-4" />{t("saveDateField")}</Btn>
        </div>
      </div>
    </Modal>
  );
}
