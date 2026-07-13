import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { apiErr } from "../lib/api";
import { Stethoscope, Languages, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const { t, lang, toggle } = useLang();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      toast.error(apiErr(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left brand panel */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-moneygreen-800 flex-col justify-between p-12"
        style={{ backgroundImage: "linear-gradient(rgba(17,34,24,0.82), rgba(17,34,24,0.88)), url('https://images.unsplash.com/photo-1758691463333-c79215e8bc3b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200')", backgroundSize: "cover", backgroundPosition: "center" }}>
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-md bg-moneygreen-500 flex items-center justify-center">
            <Stethoscope className="w-6 h-6 text-white" />
          </div>
          <span className="font-heading font-extrabold text-white text-lg">{t("appName")}</span>
        </div>
        <div>
          <h1 className="font-heading text-4xl font-extrabold text-white tracking-tight leading-tight">
            {t("tagline")}
          </h1>
          <p className="text-tan-200 mt-4 max-w-md text-base leading-relaxed">
            {t("loginSubtitle")}. Patients, appointments, telehealth, notes & billing — one calm workspace.
          </p>
        </div>
        <p className="text-tan-300 text-sm">Puerto Plata, Dominican Republic</p>
      </div>

      {/* Right form */}
      <div className="flex-1 flex flex-col items-start justify-center px-6 sm:px-16 bg-tan-100">
        <div className="w-full max-w-md">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-2 lg:hidden">
              <div className="w-9 h-9 rounded-md bg-moneygreen-600 flex items-center justify-center">
                <Stethoscope className="w-5 h-5 text-white" />
              </div>
              <span className="font-heading font-bold text-moneygreen-800">VPP Clinic</span>
            </div>
            <button onClick={toggle} data-testid="lang-toggle-login"
              className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-md border border-border text-sm font-semibold text-moneygreen-700 hover:bg-white transition-colors duration-200">
              <Languages className="w-4 h-4" />{lang === "en" ? "ES" : "EN"}
            </button>
          </div>

          <h2 className="font-heading text-3xl font-extrabold text-moneygreen-800 tracking-tight">{t("welcomeBack")}</h2>
          <p className="text-stone-500 mt-2 mb-8">{t("loginSubtitle")}</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("email")}</label>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email"
                className="mt-1.5 w-full px-4 py-2.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500"
                placeholder="you@vpp.com" />
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t("password")}</label>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password"
                className="mt-1.5 w-full px-4 py-2.5 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500"
                placeholder="••••••••" />
            </div>
            <button type="submit" disabled={loading} data-testid="login-submit"
              className="w-full py-2.5 rounded-md bg-moneygreen-600 text-white font-semibold hover:bg-moneygreen-700 transition-colors duration-200 flex items-center justify-center gap-2 disabled:opacity-60">
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? t("loggingIn") : t("login")}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
