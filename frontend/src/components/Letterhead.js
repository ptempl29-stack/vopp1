import React, { useState } from "react";
import api, { apiErr } from "../lib/api";
import { Stethoscope, Pencil, Save, X, Upload, Loader2 } from "lucide-react";
import { toast } from "sonner";

// The approved compact company header. Line order and grouping are FIXED —
// only the field contents (from Company Header Settings) ever change:
//   1) clinic name          2) RNC
//   3) DR address | DR phone        4) primary email | 2nd DR phone
//   5) WhatsApp | admin email | US phone      6) Mailing Address
// Keep this logic in sync with draw_compact_header() in the backend
// (core/folder_filing.py), which renders the same order on invoice and
// progress-note PDFs.
export const Letterhead = ({ settings }) => {
  if (!settings) return null;
  const lines = [
    settings.rnc && `RNC: ${settings.rnc}`,
    [settings.address, settings.phone].filter(Boolean).join(" | "),
    [settings.email, settings.phone2].filter(Boolean).join(" | "),
    [settings.whatsapp && `WhatsApp: ${settings.whatsapp}`, settings.admin_email, settings.phone3].filter(Boolean).join(" | "),
    settings.mailing_address && `Mailing Address: ${settings.mailing_address}`,
  ].filter(Boolean);
  return (
    <div className="border-b-2 border-moneygreen-600 pb-3 mb-6" data-testid="form-letterhead">
      <div className="flex items-start gap-3">
        {settings.logo ? (
          <img src={settings.logo} alt="logo" className="h-12 w-12 object-contain rounded-md shrink-0" data-testid="letterhead-logo" />
        ) : (
          <div className="h-12 w-12 rounded-md bg-moneygreen-600 flex items-center justify-center shrink-0">
            <Stethoscope className="w-6 h-6 text-white" />
          </div>
        )}
        <div className="min-w-0 text-xs text-stone-600 leading-snug" data-testid="letterhead-compact-header">
          <h2 className="font-heading text-base sm:text-lg font-extrabold text-moneygreen-800 tracking-tight leading-tight mb-0.5">
            {settings.clinic_name}
          </h2>
          {lines.map((ln, i) => <p key={i}>{ln}</p>)}
        </div>
      </div>
    </div>
  );
};

const cell = "w-full px-2 py-1.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm";

// Inline-editable letterhead. Saves GLOBALLY to clinic settings (PUT /settings).
export const EditableLetterhead = ({ settings, onSaved, canEdit = false, t = (x) => x }) => {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  const open = () => { setForm({ ...(settings || {}) }); setEditing(true); };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onLogo = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 650 * 1024) { toast.error("Logo too large (max ~650KB)"); return; }
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, logo: reader.result }));
    reader.readAsDataURL(file);
  };

  const save = async () => {
    if (!form.clinic_name || !form.clinic_name.trim()) { toast.error(t("clinicName") || "Clinic name required"); return; }
    setSaving(true);
    try {
      const payload = {
        clinic_name: form.clinic_name || "",
        tagline: (settings && settings.tagline) || "",
        rnc: form.rnc || "",
        address: form.address || "",
        phone: form.phone || "",
        email: form.email || "",
        phone2: form.phone2 || "",
        whatsapp: form.whatsapp || "",
        admin_email: form.admin_email || "",
        phone3: form.phone3 || "",
        mailing_address: form.mailing_address || "",
        primary_insurance: (settings && settings.primary_insurance) || "",
        logo: form.logo || "",
      };
      const r = await api.put("/settings", payload);
      onSaved && onSaved(r.data);
      setEditing(false);
      toast.success((t("save") || "Saved") + " ✓");
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSaving(false); }
  };

  if (!settings) return null;

  if (!editing) {
    return (
      <div className="relative">
        <Letterhead settings={settings} />
        {canEdit && (
          <button type="button" onClick={open} data-testid="edit-letterhead-btn"
            className="no-print absolute top-0 right-0 inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold text-moneygreen-700 border border-border bg-white hover:bg-moneygreen-50 transition-colors duration-200">
            <Pencil className="w-3.5 h-3.5" />{t("editLetterhead") || "Edit"}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="border-b-2 border-moneygreen-600 pb-4 mb-6 no-print" data-testid="edit-letterhead-form">
      <div className="flex items-center gap-4 mb-3">
        {form.logo ? (
          <img src={form.logo} alt="logo" className="h-14 w-14 object-contain rounded-md" />
        ) : (
          <div className="h-14 w-14 rounded-md bg-moneygreen-600 flex items-center justify-center shrink-0">
            <Stethoscope className="w-7 h-7 text-white" />
          </div>
        )}
        <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold text-moneygreen-700 border border-border bg-white hover:bg-moneygreen-50 cursor-pointer">
          <Upload className="w-3.5 h-3.5" />{t("logo") || "Logo"}
          <input type="file" accept="image/*" className="hidden" onChange={onLogo} data-testid="lh-logo" />
        </label>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <div><label className="text-xs font-semibold text-stone-500">{t("clinicName") || "Clinic Name"}</label>
          <input value={form.clinic_name || ""} onChange={set("clinic_name")} className={cell} data-testid="lh-clinic-name" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("rnc") || "RNC Number"}</label>
          <input value={form.rnc || ""} onChange={set("rnc")} className={cell} data-testid="lh-rnc" /></div>
        <div className="sm:col-span-2"><label className="text-xs font-semibold text-stone-500">{t("physicalAddress") || "Physical Address"}</label>
          <input value={form.address || ""} onChange={set("address")} className={cell} data-testid="lh-address" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("drPhone") || "Dominican Republic Phone Number"}</label>
          <input value={form.phone || ""} onChange={set("phone")} className={cell} data-testid="lh-phone" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("primaryEmail") || "Primary Email"}</label>
          <input value={form.email || ""} onChange={set("email")} className={cell} data-testid="lh-email" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("drPhone2") || "Additional Telephone Number"}</label>
          <input value={form.phone2 || ""} onChange={set("phone2")} className={cell} data-testid="lh-phone2" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("whatsapp") || "WhatsApp Number"}</label>
          <input value={form.whatsapp || ""} onChange={set("whatsapp")} className={cell} data-testid="lh-whatsapp" placeholder="+1 809 555 0100" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("adminEmail") || "Administrative Email"}</label>
          <input value={form.admin_email || ""} onChange={set("admin_email")} className={cell} data-testid="lh-admin-email" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("usPhone") || "Additional Telephone Number"}</label>
          <input value={form.phone3 || ""} onChange={set("phone3")} className={cell} data-testid="lh-phone3" /></div>
        <div className="sm:col-span-2"><label className="text-xs font-semibold text-stone-500">{t("mailingAddress") || "Mailing Address"}</label>
          <input value={form.mailing_address || ""} onChange={set("mailing_address")} className={cell} data-testid="lh-mailing" /></div>
      </div>
      <div className="mt-4 rounded-md border border-dashed border-border p-3 bg-tan-50" data-testid="lh-preview">
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-stone-400 mb-2">{t("headerPreview") || "Header Preview"}</p>
        <Letterhead settings={form} />
      </div>
      <div className="flex justify-end gap-2 mt-3">
        <button type="button" onClick={() => setEditing(false)} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-semibold text-stone-600 border border-border bg-white hover:bg-stone-50">
          <X className="w-4 h-4" />{t("cancel") || "Cancel"}
        </button>
        <button type="button" onClick={save} disabled={saving} data-testid="lh-save-btn"
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-semibold text-white bg-moneygreen-600 hover:bg-moneygreen-700 disabled:opacity-60">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{t("save") || "Save"}
        </button>
      </div>
    </div>
  );
};
