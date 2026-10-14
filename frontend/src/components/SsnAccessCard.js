import React, { useEffect, useState } from "react";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { Card, Btn } from "./ui-kit";
import { roleLabel } from "../lib/perms";
import { ShieldCheck, Save } from "lucide-react";
import { toast } from "sonner";

export const SsnAccessCard = () => {
  const { t } = useLang();
  const [roles, setRoles] = useState([]);
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/settings/ssn-access").then((r) => { setRoles(r.data.roles); setSel(r.data.full_roles); }).catch((e) => toast.error(apiErr(e)));
  }, []);

  const toggle = (r) => setSel((s) => (s.includes(r) ? s.filter((x) => x !== r) : [...s, r]));
  const save = async () => {
    setBusy(true);
    try { setSel((await api.put("/settings/ssn-access", { full_roles: sel })).data.full_roles); toast.success(t("save") + " ✓"); }
    catch (e) { toast.error(apiErr(e)); }
    finally { setBusy(false); }
  };

  return (
    <Card className="p-5 mt-8" data-testid="ssn-access-card">
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck className="w-5 h-5 text-moneygreen-600" />
        <h3 className="font-heading text-lg font-bold text-moneygreen-800">{t("ssnAccessTitle")}</h3>
      </div>
      <p className="text-sm text-stone-500 mb-4">{t("ssnAccessHint")}</p>
      <div className="flex flex-wrap gap-3 mb-4">
        {roles.map((r) => (
          <label key={r} className="inline-flex items-center gap-2 px-3 py-2 rounded-md border border-border text-sm cursor-pointer hover:bg-tan-50 transition-colors">
            <input type="checkbox" checked={r === "admin" || sel.includes(r)} disabled={r === "admin"}
              onChange={() => toggle(r)} data-testid={`ssn-access-${r}`} />
            <span className="capitalize">{roleLabel(r)}</span>
          </label>
        ))}
      </div>
      <Btn onClick={save} disabled={busy} data-testid="ssn-access-save"><Save className="w-4 h-4" />{t("save")}</Btn>
    </Card>
  );
};
