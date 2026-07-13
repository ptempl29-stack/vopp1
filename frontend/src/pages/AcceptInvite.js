import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiErr } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { Stethoscope, Languages, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function AcceptInvite() {
  const { token } = useParams();
  const { t, lang, toggle } = useLang();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [invalid, setInvalid] = useState(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get(`/public/invites/${token}`)
      .then((r) => setInvite(r.data))
      .catch(() => setInvalid(true))
      .finally(() => setLoading(false));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await api.post(`/public/invites/${token}/accept`, { name, password });
      localStorage.setItem("vpp_token", r.data.token);
      toast.success(t("accountCreated"));
      window.location.href = "/";
    } catch (err) {
      toast.error(apiErr(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-tan-100 px-6 py-12">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-md bg-moneygreen-600 flex items-center justify-center">
              <Stethoscope className="w-5 h-5 text-white" />
            </div>
            <span className="font-heading font-extrabold text-moneygreen-800">{invite?.clinic || t("appName")}</span>
          </div>
          <button onClick={toggle} data-testid="lang-toggle-invite"
            className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border text-sm font-semibold text-moneygreen-700 hover:bg-white transition-colors duration-200">
            <Languages className="w-4 h-4" />{lang === "en" ? "ES" : "EN"}
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-moneygreen-600" /></div>
        ) : invalid ? (
          <div className="bg-white rounded-lg border border-border p-8 text-center" data-testid="invite-invalid">
            <ShieldCheck className="w-10 h-10 text-stone-300 mx-auto mb-3" />
            <p className="text-stone-600">{t("inviteInvalid")}</p>
            <button onClick={() => navigate("/login")} className="mt-4 text-sm font-semibold text-moneygreen-700 hover:underline">{t("login")}</button>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-border p-8" data-testid="accept-invite-card">
            <h2 className="font-heading text-2xl font-extrabold text-moneygreen-800 tracking-tight">{t("acceptInviteTitle")}</h2>
            <p className="text-stone-500 mt-1.5 mb-5 text-sm">{t("acceptInviteSubtitle")}</p>
            <div className="flex items-center gap-2 p-3 rounded-md bg-tan-50 border border-border mb-5 text-sm">
              <span className="text-stone-500">{invite.email}</span>
              <span className="ml-auto inline-block px-2.5 py-1 rounded-full text-xs font-semibold capitalize bg-moneygreen-100 text-moneygreen-700">{t("invitedAs")}: {invite.role}</span>
            </div>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("fullName")}</label>
                <input required value={name} onChange={(e) => setName(e.target.value)} data-testid="invite-name-input"
                  className="mt-1.5 w-full px-4 py-2.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500" />
              </div>
              <div>
                <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("password")}</label>
                <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} data-testid="invite-password-input"
                  className="mt-1.5 w-full px-4 py-2.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500" placeholder="••••••••" />
              </div>
              <button type="submit" disabled={submitting} data-testid="accept-invite-submit"
                className="w-full py-2.5 rounded-md bg-moneygreen-600 text-white font-semibold hover:bg-moneygreen-700 transition-colors duration-200 flex items-center justify-center gap-2 disabled:opacity-60">
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                {t("createAccount")}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
