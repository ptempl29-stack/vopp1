import React, { useState } from "react";
import api, { apiErr } from "../lib/api";
import { Modal, Field, inputCls, Btn } from "./ui-kit";
import { useLang } from "../context/LanguageContext";
import { toast } from "sonner";

// Lets a clinician or biller add a brand-new ICD-10 code to the shared list
// on the spot, without needing a separate settings screen. Once saved, the
// code is immediately available (and removable) everywhere the ICD-10
// ManagedSelect dropdown is used.
export function AddIcdCodeModal({ open, onClose, onAdded }) {
  const { t } = useLang();
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const close = () => { setCode(""); setDescription(""); onClose && onClose(); };

  const submit = async (e) => {
    e.preventDefault();
    const c = code.trim();
    if (!c) return;
    setSaving(true);
    try {
      const r = await api.post("/icd-codes", { code: c, description: description.trim() });
      toast.success(t("save") + " ✓");
      onAdded && onAdded(r.data);
      close();
    } catch (err) { toast.error(apiErr(err)); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={open} onClose={close} title={t("newIcdCode")}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("icd10Code")}>
          <input required autoFocus value={code} onChange={(e) => setCode(e.target.value)}
            className={inputCls} placeholder="e.g. F41.1" data-testid="add-icd-code" />
        </Field>
        <Field label={t("description")}>
          <input value={description} onChange={(e) => setDescription(e.target.value)}
            className={inputCls} data-testid="add-icd-desc" />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="outline" type="button" onClick={close}>{t("cancel")}</Btn>
          <Btn type="submit" disabled={saving} data-testid="save-icd-btn">{t("save")}</Btn>
        </div>
      </form>
    </Modal>
  );
}
