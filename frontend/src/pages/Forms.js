import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { printSection } from "../lib/print";
import { useSelection, bulkDelete } from "../lib/bulk";
import { useSearchParams } from "react-router-dom";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { Letterhead } from "../components/Letterhead";
import { Plus, ClipboardList, CheckCircle2, Link2, Eye, Upload, Download, ExternalLink, Loader2, PenLine, Printer, FileDown, FileText, FileSpreadsheet, MessageCircle, Send, Trash2, Mail, FolderInput, Pencil } from "lucide-react";
import { toast } from "sonner";

const types = ["Intake", "Consent", "Medical History", "Insurance", "Referral"];
const toneMap = { sent: "amber", pending: "amber", received: "green" };

const isSigned = (f) => !!f.responses && Object.values(f.responses).some(
  (v) => typeof v === "string" && v.startsWith("data:image"));

export default function Forms() {
  const { t } = useLang();
  const sel = useSelection();
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status");
  const [forms, setForms] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({ patient_id: "", title: "", form_type: "Intake", status: "sent", external_url: "", recipient_email: "" });
  const [upl, setUpl] = useState({ title: "", form_type: "Uploaded", patient_id: "", file: null });
  const [emailModal, setEmailModal] = useState(null);
  const [folderModal, setFolderModal] = useState(null);
  const [folderSubs, setFolderSubs] = useState([]);
  const [formModal, setFormModal] = useState(null);
  const [sendingEmail, setSendingEmail] = useState(false);

  const load = () => api.get("/forms").then((r) => setForms(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get("/patients").then((r) => setPatients(r.data)).catch(() => {});
    api.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const copyLink = (f) => {
    const url = `${window.location.origin}/form/${f.public_token}`;
    navigator.clipboard.writeText(url).then(() => toast.success(t("linkCopied")))
      .catch(() => toast.error(url));
  };

  const downloadAttachment = async (f) => {
    try {
      const res = await api.get(`/forms/${f.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = f.attachment?.filename || "attachment";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { toast.error(apiErr(err)); }
  };

  const downloadTemplate = async (kind) => {
    try {
      const res = await api.get(`/forms/blank-template/${kind}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = kind === "docx" ? "blank_form.docx" : kind === "xlsx" ? "blank_spreadsheet.xlsx" : "blank_form.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { toast.error(apiErr(err)); }
  };

  const sendWhatsApp = (f) => {
    const url = `${window.location.origin}/form/${f.public_token}`;
    const clinic = settings?.clinic_name || "Veterans of Puerto Plata";
    const msg = encodeURIComponent(`${clinic}: Please complete your form "${f.title}": ${url}`);
    const p = patients.find((x) => x.id === f.patient_id);
    const phone = (p?.phone || "").replace(/\D/g, "");
    window.open(`https://wa.me/${phone}?text=${msg}`, "_blank", "noopener,noreferrer");
  };

  const sendSms = async (f) => {
    try {
      const res = await api.post(`/forms/${f.id}/send-sms`);
      if (res.data.configured === false) toast.info(t("smsNotConfigured"));
      else if (res.data.sent) toast.success(t("smsSent"));
      else toast.error(t("smsFailed"));
    } catch (err) { toast.error(apiErr(err)); }
  };

  const save = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, recipient_email: form.recipient_email || null, link_base: window.location.origin };
      const res = await api.post("/forms", payload);
      if (res.data.email_sent) toast.success(t("emailSent"));
      else if (form.recipient_email) toast.info(t("emailNotSent"));
      else toast.success(t("save") + " ✓");
      setOpen(false); setForm({ patient_id: "", title: "", form_type: "Intake", status: "sent", external_url: "", recipient_email: "" }); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const onPatientSelect = (e) => {
    const pid = e.target.value;
    const p = patients.find((x) => x.id === pid);
    setForm((f) => ({ ...f, patient_id: pid, recipient_email: p?.email || f.recipient_email }));
  };

  const uploadFile = async (e) => {
    e.preventDefault();
    if (!upl.file) { toast.error(t("chooseFile")); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", upl.file);
      fd.append("title", upl.title);
      fd.append("form_type", upl.form_type);
      fd.append("patient_id", upl.patient_id);
      await api.post("/forms/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(t("uploadForm") + " ✓");
      setUploadOpen(false); setUpl({ title: "", form_type: "Uploaded", patient_id: "", file: null }); load();
    } catch (err) { toast.error(apiErr(err)); }
    finally { setUploading(false); }
  };

  const markReceived = async (id) => {
    try { await api.put(`/forms/${id}/status`, null, { params: { status: "received" } }); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const removeForm = async (id) => {
    try { await api.delete(`/forms/${id}`); load(); } catch (err) { toast.error(apiErr(err)); }
  };
  const removeSelected = async () => {
    try { await bulkDelete("/forms/bulk-delete", [...sel.selected], t); sel.clear(); load(); }
    catch (err) { toast.error(apiErr(err)); }
  };

  const openForm = (f) => {
    setFormModal({
      id: f.id, title: f.title || "", form_type: f.form_type || "Intake", status: f.status || "sent",
      patient_id: f.patient_id || "", external_url: f.external_url || "", recipient_email: f.recipient_email || "",
      responses: f.responses ? { ...f.responses } : null, template: f.template || [],
      patient_name: f.patient_name, attachment: f.attachment, public_token: f.public_token,
    });
  };
  const saveFormEdit = async (e) => {
    e.preventDefault();
    const m = formModal;
    try {
      await api.put(`/forms/${m.id}`, {
        title: m.title, form_type: m.form_type, status: m.status,
        patient_id: m.patient_id || null, external_url: m.external_url || "",
        recipient_email: m.recipient_email || null, responses: m.responses || undefined,
      });
      toast.success(t("saveForm") + " ✓"); setFormModal(null); load();
    } catch (err) { toast.error(apiErr(err)); }
  };

  const openEmail = (f) => {
    const p = patients.find((x) => x.id === f.patient_id);
    setEmailModal({ fid: f.id, title: f.title, recipients: [f.recipient_email || p?.email || ""] });
  };
  const sendEmail = async (e) => {
    e.preventDefault();
    const recips = (emailModal.recipients || []).map((r) => r.trim()).filter(Boolean);
    if (!recips.length) { toast.error(t("recipientEmail")); return; }
    setSendingEmail(true);
    try {
      const res = await api.post(`/forms/${emailModal.fid}/send-email`, { recipients: recips });
      if (res.data.configured === false) toast.info(t("emailNotConfigured"));
      else if (res.data.sent > 0) {
        toast.success(`${res.data.sent}/${res.data.total} ${t("emailSentOk")}`);
        if (res.data.failed?.length) toast.error(`${t("emailFailed")} ${res.data.failed.join(", ")}`);
        setEmailModal(null); load();
      } else toast.error(t("emailFailed"));
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSendingEmail(false); }
  };

  const openFolderMove = async (f) => {
    setFolderModal({ fid: f.id, title: f.title, patient_id: f.patient_id || "", subfolder_id: "" });
    setFolderSubs([]);
    if (f.patient_id) {
      try { setFolderSubs((await api.get(`/folders/${f.patient_id}`)).data.subfolders || []); } catch { /* noop */ }
    }
  };
  const changeFolderPatient = async (pid) => {
    setFolderModal((m) => ({ ...m, patient_id: pid, subfolder_id: "" }));
    if (pid) { try { setFolderSubs((await api.get(`/folders/${pid}`)).data.subfolders || []); } catch { setFolderSubs([]); } }
    else setFolderSubs([]);
  };
  const doMoveToFolder = async (e) => {
    e.preventDefault();
    if (!folderModal.patient_id) { toast.error(t("selectPatient")); return; }
    try {
      const res = await api.post(`/forms/${folderModal.fid}/to-folder`, {
        patient_id: folderModal.patient_id, subfolder_id: folderModal.subfolder_id || null });
      toast.success(`${t("movedToFolder")} (${res.data.patient_name})`); setFolderModal(null);
    } catch (err) { toast.error(apiErr(err)); }
  };

  const filtered = forms.filter((f) => {
    if (!statusFilter) return true;
    if (statusFilter === "pending") return ["sent", "pending"].includes(f.status);
    return f.status === statusFilter;
  });

  return (
    <div>
      <PageHeader title={t("forms")} subtitle={`${forms.length}`}
        action={<div className="flex gap-2 flex-wrap">
          <Btn variant="outline" onClick={() => downloadTemplate("docx")} data-testid="tpl-docx-btn" className="!px-2.5" title="Blank Word"><FileText className="w-4 h-4" />Word</Btn>
          <Btn variant="outline" onClick={() => downloadTemplate("xlsx")} data-testid="tpl-xlsx-btn" className="!px-2.5" title="Blank Excel"><FileSpreadsheet className="w-4 h-4" />Excel</Btn>
          <Btn variant="outline" onClick={() => downloadTemplate("pdf")} data-testid="tpl-pdf-btn" className="!px-2.5" title="Blank PDF"><FileDown className="w-4 h-4" />PDF</Btn>
          <Btn variant="outline" onClick={() => setUploadOpen(true)} data-testid="upload-form-btn"><Upload className="w-4 h-4" />{t("uploadForm")}</Btn>
          <Btn onClick={() => setOpen(true)} data-testid="add-form-btn"><Plus className="w-4 h-4" />{t("newForm")}</Btn>
        </div>} />

      {(sel.count > 0 || statusFilter) && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {statusFilter && (
            <Badge tone="amber" className="flex items-center gap-1">{t(statusFilter)}
              <button onClick={() => { params.delete("status"); setParams(params); }} data-testid="clear-form-filter" className="ml-1 underline">{t("clearFilter")}</button>
            </Badge>
          )}
          {sel.count > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-sm text-stone-500">{sel.count}</span>
              <Btn variant="danger" onClick={removeSelected} data-testid="bulk-delete-forms"><Trash2 className="w-4 h-4" />{t("deleteSelected")}</Btn>
              <Btn variant="outline" onClick={sel.clear} data-testid="deselect-forms">{t("deselectAll")}</Btn>
            </div>
          )}
        </div>
      )}

      <Card className="overflow-hidden">
        {filtered.length === 0 ? <Empty text={t("noData")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-bold uppercase tracking-wider text-stone-500 border-b border-border">
                  <th className="px-4 py-3 w-8">
                    <input type="checkbox" data-testid="select-all-forms"
                      checked={filtered.length > 0 && sel.count >= filtered.length}
                      onChange={() => sel.toggleAll(filtered.map((f) => f.id))}
                      className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                  </th>
                  <th className="px-5 py-3">{t("title")}</th>
                  <th className="px-5 py-3">{t("formType")}</th>
                  <th className="px-5 py-3 hidden md:table-cell">{t("patient")}</th>
                  <th className="px-5 py-3">{t("status")}</th>
                  <th className="px-5 py-3 text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((f, i) => (
                  <motion.tr key={f.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    data-testid={`form-row-${f.id}`}
                    className={`border-b border-border/60 hover:bg-tan-50 transition-colors duration-200 ${sel.has(f.id) ? "bg-moneygreen-50" : i % 2 ? "bg-tan-50/40" : ""}`}>
                    <td className="px-4 py-3">
                      <input type="checkbox" checked={sel.has(f.id)} onChange={() => sel.toggle(f.id)}
                        data-testid={`select-form-${f.id}`} className="w-4 h-4 accent-moneygreen-600 cursor-pointer" />
                    </td>
                    <td className="px-5 py-3">
                      <button type="button" onClick={() => openForm(f)} data-testid={`open-form-${f.id}`}
                        className="flex items-center gap-2.5 text-left hover:underline">
                        <ClipboardList className="w-4 h-4 text-moneygreen-500" />
                        <span className="font-semibold text-moneygreen-800">{f.title}</span>
                      </button>
                    </td>
                    <td className="px-5 py-3 text-stone-600">{f.form_type}</td>
                    <td className="px-5 py-3 hidden md:table-cell text-stone-600">{f.patient_name}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <Badge tone={toneMap[f.status] || "gray"}>{t(f.status)}</Badge>
                        {isSigned(f) && (
                          <span data-testid={`signed-badge-${f.id}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-moneygreen-100 text-moneygreen-700">
                            <PenLine className="w-3 h-3" />{t("signed")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        {f.attachment && (
                          <Btn variant="ghost" onClick={() => downloadAttachment(f)} data-testid={`download-form-${f.id}`} className="!px-2" title={t("download")}>
                            <Download className="w-4 h-4" />
                          </Btn>
                        )}
                        {f.external_url && (
                          <a href={f.external_url} target="_blank" rel="noopener noreferrer" data-testid={`open-link-${f.id}`}
                            className="inline-flex items-center px-2 py-2 rounded-md text-stone-500 hover:text-moneygreen-700 hover:bg-tan-100 transition-colors duration-200" title={t("openLink")}>
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        )}
                        {!f.attachment && (
                          <Btn variant="ghost" onClick={() => copyLink(f)} data-testid={`copy-link-${f.id}`} className="!px-2" title={t("copyLink")}>
                            <Link2 className="w-4 h-4" />
                          </Btn>
                        )}
                        {f.public_token && (
                          <Btn variant="ghost" onClick={() => sendWhatsApp(f)} data-testid={`whatsapp-${f.id}`} className="!px-2" title={t("sendWhatsApp")}>
                            <MessageCircle className="w-4 h-4" />
                          </Btn>
                        )}
                        {f.public_token && f.patient_id && (
                          <Btn variant="ghost" onClick={() => sendSms(f)} data-testid={`sms-${f.id}`} className="!px-2" title={t("sendSms")}>
                            <Send className="w-4 h-4" />
                          </Btn>
                        )}
                        <Btn variant="ghost" onClick={() => openEmail(f)} data-testid={`email-form-${f.id}`} className="!px-2" title={t("sendByEmail")}>
                          <Mail className="w-4 h-4" />
                        </Btn>
                        <Btn variant="ghost" onClick={() => openFolderMove(f)} data-testid={`to-folder-${f.id}`} className="!px-2" title={t("moveToFolderTitle")}>
                          <FolderInput className="w-4 h-4" />
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
                        <Btn variant="ghost" onClick={() => removeForm(f.id)} data-testid={`delete-form-${f.id}`} className="!px-2 !text-destructive" title={t("delete")}>
                          <Trash2 className="w-4 h-4" />
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

      <Modal open={open} onClose={() => setOpen(false)} title={t("newForm")}>
        <form onSubmit={save} className="space-y-4">
          <Field label={t("title")}><input required value={form.title} onChange={set("title")} className={inputCls} data-testid="ff-title" /></Field>
          <Field label={t("formType")}>
            <select value={form.form_type} onChange={set("form_type")} className={inputCls} data-testid="ff-type">
              {types.map((ty) => <option key={ty} value={ty}>{ty}</option>)}
            </select>
          </Field>
          <Field label={t("patient")}>
            <select value={form.patient_id} onChange={onPatientSelect} className={inputCls}>
              <option value="">—</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </Field>
          <Field label={t("emailFormLink")}>
            <input type="email" value={form.recipient_email || ""} onChange={set("recipient_email")} className={inputCls} data-testid="ff-recipient" placeholder="patient@email.com" />
            <p className="text-xs text-stone-400 mt-1">{t("emailLinkHint")}</p>
          </Field>
          <Field label={t("externalLink")}>
            <input value={form.external_url} onChange={set("external_url")} className={inputCls} data-testid="ff-url" placeholder="https://..." />
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

      <Modal open={uploadOpen} onClose={() => setUploadOpen(false)} title={t("uploadForm")}>
        <form onSubmit={uploadFile} className="space-y-4">
          <Field label={t("title")}><input required value={upl.title} onChange={(e) => setUpl({ ...upl, title: e.target.value })} className={inputCls} data-testid="uplf-title" /></Field>
          <Field label={t("formType")}>
            <select value={upl.form_type} onChange={(e) => setUpl({ ...upl, form_type: e.target.value })} className={inputCls}>
              {["Uploaded", ...types].map((ty) => <option key={ty} value={ty}>{ty}</option>)}
            </select>
          </Field>
          <Field label={t("patient")}>
            <select value={upl.patient_id} onChange={(e) => setUpl({ ...upl, patient_id: e.target.value })} className={inputCls}>
              <option value="">—</option>
              {patients.map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}</option>)}
            </select>
          </Field>
          <Field label={t("uploadFromComputer")}>
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,.txt" required
              onChange={(e) => setUpl({ ...upl, file: e.target.files[0] })} data-testid="uplf-file"
              className="w-full text-sm text-stone-600 file:mr-3 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-moneygreen-600 file:text-white file:font-semibold file:cursor-pointer hover:file:bg-moneygreen-700" />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Btn variant="outline" type="button" onClick={() => setUploadOpen(false)}>{t("cancel")}</Btn>
            <Btn type="submit" disabled={uploading} data-testid="save-upload-btn">
              {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              {uploading ? t("uploading") : t("uploadForm")}
            </Btn>
          </div>
        </form>
      </Modal>

      <Modal open={!!viewing} onClose={() => setViewing(null)} title={t("responses")}>
        {viewing && (
          <div className="space-y-3">
            <div id="form-print" className="space-y-3" data-testid="responses-view">
              <Letterhead settings={settings} />
              <div className="flex items-baseline justify-between border-b border-border pb-2">
                <p className="font-heading font-bold text-moneygreen-800">{viewing.title}</p>
                <div className="text-right text-xs text-stone-500">
                  <p>{viewing.form_type}{viewing.patient_name ? ` · ${viewing.patient_name}` : ""}</p>
                  {isSigned(viewing) && <p className="text-moneygreen-600 font-semibold">{t("signed")}</p>}
                </div>
              </div>
              {viewing.responses && Object.keys(viewing.responses).length > 0 ? (
                (viewing.template || []).filter((fld) => viewing.responses[fld.name] !== undefined && viewing.responses[fld.name] !== "").map((fld) => (
                  <div key={fld.name} className="border-b border-border pb-2">
                    <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{fld.en}</p>
                    {String(viewing.responses[fld.name]).startsWith("data:image") ? (
                      <img src={viewing.responses[fld.name]} alt={fld.en} className="h-16 object-contain mt-1" data-testid={`resp-sig-${fld.name}`} />
                    ) : (
                      <p className="text-sm text-moneygreen-800 mt-0.5">{String(viewing.responses[fld.name])}</p>
                    )}
                  </div>
                ))
              ) : <p className="text-sm text-stone-500">{t("noResponses")}</p>}
            </div>
            <div className="flex justify-end gap-2 pt-2 no-print">
              <Btn variant="outline" onClick={() => printSection("form-print")} data-testid="form-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
              <Btn variant="outline" onClick={() => printSection("form-print")} data-testid="form-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
            </div>
          </div>
        )}
      </Modal>

      {/* View / Edit form */}
      <Modal open={!!formModal} onClose={() => setFormModal(null)} title={t("viewEditForm")} wide>
        {formModal && (
          <form onSubmit={saveFormEdit} className="space-y-4" data-testid="form-edit-modal">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label={t("title")}><input required value={formModal.title} onChange={(e) => setFormModal({ ...formModal, title: e.target.value })} className={inputCls} data-testid="fm-title" /></Field>
              <Field label={t("formType")}>
                <select value={formModal.form_type} onChange={(e) => setFormModal({ ...formModal, form_type: e.target.value })} className={inputCls} data-testid="fm-type">
                  {["Uploaded", ...types].map((ty) => <option key={ty} value={ty}>{ty}</option>)}
                </select>
              </Field>
              <Field label={t("patient")}>
                <select value={formModal.patient_id} onChange={(e) => setFormModal({ ...formModal, patient_id: e.target.value })} className={inputCls} data-testid="fm-patient">
                  <option value="">—</option>
                  {patients.map((p) => <option key={p.id} value={p.id}>{`${p.first_name} ${p.last_name}`}</option>)}
                </select>
              </Field>
              <Field label={t("status")}>
                <select value={formModal.status} onChange={(e) => setFormModal({ ...formModal, status: e.target.value })} className={inputCls} data-testid="fm-status">
                  <option value="sent">{t("sent")}</option><option value="pending">{t("pending")}</option><option value="received">{t("received")}</option>
                </select>
              </Field>
              <Field label={t("recipientEmail")}><input type="email" value={formModal.recipient_email} onChange={(e) => setFormModal({ ...formModal, recipient_email: e.target.value })} className={inputCls} data-testid="fm-recipient" placeholder="patient@email.com" /></Field>
              <Field label={t("externalLink")}><input value={formModal.external_url} onChange={(e) => setFormModal({ ...formModal, external_url: e.target.value })} className={inputCls} data-testid="fm-url" placeholder="https://..." /></Field>
            </div>

            {formModal.responses && Object.keys(formModal.responses).length > 0 && (
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500 mb-2">{t("editResponses")}</p>
                <div className="space-y-3 border border-border rounded-md p-3 bg-tan-50/40 max-h-72 overflow-y-auto custom-scroll">
                  {Object.entries(formModal.responses).map(([k, v]) => {
                    const fld = (formModal.template || []).find((x) => x.name === k);
                    const labelTxt = fld ? fld.en : k;
                    if (typeof v === "string" && v.startsWith("data:image")) {
                      return (
                        <div key={k}>
                          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">{labelTxt} · {t("signatureOnFile")}</p>
                          <img src={v} alt={labelTxt} className="h-14 object-contain mt-1" />
                        </div>
                      );
                    }
                    return (
                      <div key={k}>
                        <label className="text-xs font-bold uppercase tracking-wider text-stone-500">{labelTxt}</label>
                        <input value={String(v)} data-testid={`fm-resp-${k}`}
                          onChange={(e) => setFormModal({ ...formModal, responses: { ...formModal.responses, [k]: e.target.value } })}
                          className={`${inputCls} mt-1`} />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="flex flex-wrap justify-between gap-2 pt-2 border-t border-border">
              <div className="flex flex-wrap gap-2">
                <Btn type="button" variant="outline" onClick={() => { openEmail(formModal); }} data-testid="fm-email-btn"><Mail className="w-4 h-4" />{t("sendByEmail")}</Btn>
                <Btn type="button" variant="outline" onClick={() => { openFolderMove(formModal); }} data-testid="fm-folder-btn"><FolderInput className="w-4 h-4" />{t("moveToFolderBtn")}</Btn>
                <Btn type="button" variant="danger" onClick={() => { removeForm(formModal.id); setFormModal(null); }} data-testid="fm-delete-btn"><Trash2 className="w-4 h-4" />{t("delete")}</Btn>
              </div>
              <div className="flex gap-2">
                <Btn variant="outline" type="button" onClick={() => setFormModal(null)}>{t("cancel")}</Btn>
                <Btn type="submit" data-testid="fm-save-btn"><Pencil className="w-4 h-4" />{t("saveForm")}</Btn>
              </div>
            </div>
          </form>
        )}
      </Modal>

      {/* Send by email */}
      <Modal open={!!emailModal} onClose={() => setEmailModal(null)} title={t("emailForm")}>
        {emailModal && (
          <form onSubmit={sendEmail} className="space-y-4" data-testid="email-modal">
            <p className="text-sm text-stone-600">{emailModal.title}</p>
            <div>
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("recipientEmail")}</label>
              <div className="mt-1.5 space-y-2">
                {emailModal.recipients.map((r, idx) => (
                  <div key={idx} className="flex gap-2">
                    <input required={idx === 0} type="email" value={r}
                      onChange={(e) => { const rs = [...emailModal.recipients]; rs[idx] = e.target.value; setEmailModal({ ...emailModal, recipients: rs }); }}
                      className={inputCls} data-testid={`email-recipient-${idx}`} placeholder="patient@email.com" />
                    {emailModal.recipients.length > 1 && (
                      <Btn type="button" variant="ghost" className="!px-2 !text-destructive" data-testid={`remove-recipient-${idx}`}
                        onClick={() => setEmailModal({ ...emailModal, recipients: emailModal.recipients.filter((_, i) => i !== idx) })}>
                        <Trash2 className="w-4 h-4" />
                      </Btn>
                    )}
                  </div>
                ))}
              </div>
              <button type="button" data-testid="add-recipient-btn"
                onClick={() => setEmailModal({ ...emailModal, recipients: [...emailModal.recipients, ""] })}
                className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-moneygreen-700 hover:text-moneygreen-800">
                <Plus className="w-4 h-4" />{t("addRecipient")}
              </button>
              <p className="text-xs text-stone-400 mt-1">{t("anyEmailHint")}</p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setEmailModal(null)}>{t("cancel")}</Btn>
              <Btn type="submit" disabled={sendingEmail} data-testid="send-email-btn">
                {sendingEmail ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}{t("sendEmailBtn")}
              </Btn>
            </div>
          </form>
        )}
      </Modal>

      {/* Move to patient folder */}
      <Modal open={!!folderModal} onClose={() => setFolderModal(null)} title={t("moveToFolderTitle")}>
        {folderModal && (
          <form onSubmit={doMoveToFolder} className="space-y-4" data-testid="folder-move-modal">
            <p className="text-sm text-stone-600">{folderModal.title}</p>
            <Field label={t("targetPatient")}>
              <select value={folderModal.patient_id} onChange={(e) => changeFolderPatient(e.target.value)} className={inputCls} data-testid="fm-move-patient">
                <option value="">{t("selectPatient")}</option>
                {patients.map((p) => <option key={p.id} value={p.id}>{`${p.first_name} ${p.last_name}`}</option>)}
              </select>
            </Field>
            <Field label={t("targetFolder")}>
              <select value={folderModal.subfolder_id} onChange={(e) => setFolderModal({ ...folderModal, subfolder_id: e.target.value })} className={inputCls} data-testid="fm-move-subfolder">
                <option value="">{t("unfiled")}</option>
                {folderSubs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <Btn variant="outline" type="button" onClick={() => setFolderModal(null)}>{t("cancel")}</Btn>
              <Btn type="submit" data-testid="confirm-to-folder-btn"><FolderInput className="w-4 h-4" />{t("moveToFolderBtn")}</Btn>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
