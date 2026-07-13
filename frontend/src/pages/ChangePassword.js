import React, { useState } from "react";
import api, { apiErr } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Stethoscope, KeyRound, Loader2, Languages } from "lucide-react";
import { toast } from "sonner";

export default function ChangePassword() {
  const { t, lang, toggle } = useLang();
  const { refreshUser, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (next !== confirm) { toast.error(t("passwordsNoMatch")); return; }
    setBusy(true);
    try {
      const r = await api.post("/auth/change-password", { current_password: current, new_password: next });
      localStorage.setItem("vpp_token", r.data.token);
      toast.success(t("passwordChanged"));
      await refreshUser();
    } catch (err) {
      toast.error(apiErr(err));
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-tan-100 px-6 py-12" data-testid="force-change-password">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-md bg-moneygreen-600 flex items-center justify-center"><Stethoscope className="w-5 h-5 text-white" /></div>
            <span className="font-heading font-extrabold text-moneygreen-800">{t("appName")}</span>
          </div>
          <button onClick={toggle} className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border text-sm font-semibold text-moneygreen-700 hover:bg-white transition-colors duration-200">
            <Languages className="w-4 h-4" />{lang === "en" ? "ES" : "EN"}
          </button>
        </div>
        <div className="bg-white rounded-lg border border-border p-8">
          <div className="w-11 h-11 rounded-md bg-moneygreen-100 flex items-center justify-center text-moneygreen-600 mb-4"><KeyRound className="w-5 h-5" /></div>
          <h2 className="font-heading text-2xl font-extrabold text-moneygreen-800 tracking-tight">{t("mustChangeTitle")}</h2>
          <p className="text-stone-500 mt-1.5 mb-5 text-sm">{t("mustChangeSubtitle")}</p>
          <form onSubmit={submit} className="space-y-4">
            {[["current", t("currentPassword"), current, setCurrent], ["next", t("newPassword"), next, setNext], ["confirm", t("confirmPassword"), confirm, setConfirm]].map(([id, label, val, setter]) => (
              <div key={id}>
                <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{label}</label>
                <input type="password" required minLength={id === "current" ? 1 : 6} value={val} onChange={(e) => setter(e.target.value)}
                  data-testid={`cp-${id}`} className="mt-1.5 w-full px-4 py-2.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500" placeholder="••••••••" />
              </div>
            ))}
            <button type="submit" disabled={busy} data-testid="cp-submit"
              className="w-full py-2.5 rounded-md bg-moneygreen-600 text-white font-semibold hover:bg-moneygreen-700 transition-colors duration-200 flex items-center justify-center gap-2 disabled:opacity-60">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}{t("setNewPassword")}
            </button>
          </form>
          <button onClick={logout} className="mt-4 w-full text-center text-sm text-stone-400 hover:text-stone-600">{t("logout")}</button>
        </div>
      </div>
    </div>
  );
}
