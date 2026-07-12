import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { PageHeader, Modal, Field, inputCls, Btn, Badge, Empty, Card } from "../components/ui-kit";
import { Letterhead } from "../components/Letterhead";
import { Plus, ClipboardList, CheckCircle2, Link2, Eye, Upload, Download, ExternalLink, Loader2, PenLine, Printer, FileDown } from "lucide-react";
import { toast } from "sonner";

const types = ["Intake", "Consent", "Medical History", "Insurance", "Referral"];
const toneMap = { sent: "amber", pending: "amber", received: "green" };

const isSigned = (f) => !!f.responses && Object.values(f.responses).some(
  (v) => typeof v === "string" && v.startsWith("data:image"));

export default function Forms() {
  const { t } = useLang();
  const [forms, setForms] = useState([]);
  const [patients, setPatients] = useState([]);
  const [open, setOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({ patient_id: "", title: "", form_type: "Intake", status: "sent", external_url: "", recipient_email: "" });
  const [upl, setUpl] = useState({ title: "", form_type: "Uploaded", patient_id: "", file: null });

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

  const save = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post("/forms", { ...form, link_base: window.location.origin });
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

  return (
    <div>
      <PageHeader title={t("forms")} subtitle={`${forms.length}`}
        action={<div className="flex gap-2">
          <Btn variant="outline" onClick={() => setUploadOpen(true)} data-testid="upload-form-btn"><Upload className="w-4 h-4" />{t("uploadForm")}</Btn>
          <Btn onClick={() => setOpen(true)} data-testid="add-form-btn"><Plus className="w-4 h-4" />{t("newForm")}</Btn>
        </div>} />

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
              <Btn variant="outline" onClick={() => window.print()} data-testid="form-save-pdf-btn"><FileDown className="w-4 h-4" />{t("saveAsPdf")}</Btn>
              <Btn variant="outline" onClick={() => window.print()} data-testid="form-print-btn"><Printer className="w-4 h-4" />{t("print")}</Btn>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
