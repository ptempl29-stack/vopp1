import React, { useState } from "react";
import api, { apiErr } from "../lib/api";
import { Stethoscope, MapPin, Phone, Mail, Pencil, Save, X, Upload, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const Letterhead = ({ settings }) => {
  if (!settings) return null;
  return (
    <div className="border-b-2 border-moneygreen-600 pb-4 mb-6" data-testid="form-letterhead">
      <div className="flex items-center gap-4">
        {settings.logo ? (
          <img src={settings.logo} alt="logo" className="h-14 w-14 object-contain rounded-md" data-testid="letterhead-logo" />
        ) : (
          <div className="h-14 w-14 rounded-md bg-moneygreen-600 flex items-center justify-center shrink-0">
            <Stethoscope className="w-7 h-7 text-white" />
          </div>
        )}
        <div className="min-w-0">
          <h2 className="font-heading text-xl sm:text-2xl font-extrabold text-moneygreen-800 tracking-tight leading-tight">
            {settings.clinic_name}
          </h2>
          {settings.tagline && <p className="text-sm text-stone-500">{settings.tagline}</p>}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-xs text-stone-500">
        {settings.address && <span className="inline-flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{settings.address}</span>}
        {settings.phone && <span className="inline-flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{settings.phone}</span>}
        {settings.email && <span className="inline-flex items-center gap-1"><Mail className="w-3.5 h-3.5" />{settings.email}</span>}
      </div>
      {(settings.mailing_address || settings.primary_insurance) && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 mt-1 text-xs text-stone-500">
          {settings.mailing_address && <span><span className="font-semibold text-stone-600">Mailing Address:</span> {settings.mailing_address}</span>}
          {settings.primary_insurance && <span><span className="font-semibold text-stone-600">Primary Insurance:</span> {settings.primary_insurance}</span>}
        </div>
      )}
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
        tagline: form.tagline || "",
        address: form.address || "",
        phone: form.phone || "",
        email: form.email || "",
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
        <div><label className="text-xs font-semibold text-stone-500">{t("tagline_label") || "Tagline"}</label>
          <input value={form.tagline || ""} onChange={set("tagline")} className={cell} data-testid="lh-tagline" /></div>
        <div className="sm:col-span-2"><label className="text-xs font-semibold text-stone-500">{t("physicalAddress") || "Physical Address"}</label>
          <input value={form.address || ""} onChange={set("address")} className={cell} data-testid="lh-address" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("email") || "Email"}</label>
          <input value={form.email || ""} onChange={set("email")} className={cell} data-testid="lh-email" /></div>
        <div><label className="text-xs font-semibold text-stone-500">{t("phone") || "Phone"}</label>
          <input value={form.phone || ""} onChange={set("phone")} className={cell} data-testid="lh-phone" /></div>
        <div className="sm:col-span-2"><label className="text-xs font-semibold text-stone-500">{t("mailingAddress") || "Mailing Address"}</label>
          <input value={form.mailing_address || ""} onChange={set("mailing_address")} className={cell} data-testid="lh-mailing" /></div>
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
