import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { useLang } from "../context/LanguageContext";
import { SignaturePad } from "../components/SignaturePad";
import { Stethoscope, Languages, Loader2, CheckCircle2, FileWarning } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PublicForm() {
  const { token } = useParams();
  const { t, lang, toggle } = useLang();
  const [form, setForm] = useState(null);
  const [state, setState] = useState("loading"); // loading | ready | done | error | already
  const [values, setValues] = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    axios.get(`${API}/public/forms/${token}`)
      .then((r) => {
        setForm(r.data);
        if (r.data.status === "received") setState("already");
        else setState("ready");
      })
      .catch(() => setState("error"));
  }, [token]);

  const set = (name, val) => setValues((v) => ({ ...v, [name]: val }));

  const submit = async (e) => {
    e.preventDefault();
    const missing = (form.template || []).filter((f) => f.required && !values[f.name]);
    if (missing.length) { setState("ready"); alert(`${t("required")}: ${missing.map((m) => m[lang]).join(", ")}`); return; }
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/forms/${token}/submit`, { responses: values });
      setState("done");
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (typeof d === "string" && d.includes("already")) setState("already");
      else setState("error");
    } finally { setSubmitting(false); }
  };

  const Shell = ({ children }) => (
    <div className="min-h-screen bg-tan-100 flex flex-col">
      <header className="h-16 bg-moneygreen-800 flex items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-md bg-moneygreen-500 flex items-center justify-center">
            <Stethoscope className="w-5 h-5 text-white" />
          </div>
          <span className="font-heading font-extrabold text-white text-sm">Veterans of Puerto Plata</span>
        </div>
        <button onClick={toggle} data-testid="public-lang-toggle"
          className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-moneygreen-700 text-tan-100 text-sm font-semibold hover:bg-moneygreen-600 transition-colors duration-200">
          <Languages className="w-4 h-4" />{lang === "en" ? "ES" : "EN"}
        </button>
      </header>
      <main className="flex-1 flex items-start justify-center p-4 sm:p-8">
        <div className="w-full max-w-2xl">{children}</div>
      </main>
    </div>
  );

  if (state === "loading")
    return <Shell><div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-moneygreen-600" /></div></Shell>;

  if (state === "error")
    return <Shell><div className="bg-white rounded-lg border border-border p-10 text-center" data-testid="public-form-error">
      <FileWarning className="w-12 h-12 text-stone-400 mx-auto mb-4" />
      <h2 className="font-heading text-xl font-bold text-moneygreen-800">{t("formNotFound")}</h2>
    </div></Shell>;

  if (state === "done" || state === "already")
    return <Shell><div className="bg-white rounded-lg border border-border p-10 text-center" data-testid="public-form-success">
      <CheckCircle2 className="w-14 h-14 text-moneygreen-600 mx-auto mb-4" />
      <h2 className="font-heading text-2xl font-extrabold text-moneygreen-800">{t("thankYou")}</h2>
      <p className="text-stone-500 mt-2">{state === "already" ? t("alreadySubmitted") : t("formSubmitted")}</p>
    </div></Shell>;

  return (
    <Shell>
      <div className="bg-white rounded-lg border border-border p-6 sm:p-8">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">{form.form_type}</p>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-moneygreen-800 tracking-tight mt-1">{form.title}</h1>
        <p className="text-stone-500 mt-2">
          {form.patient_first_name ? `${t("hello")}, ${form.patient_first_name}. ` : ""}{t("patientFormIntro")}
        </p>

        <form onSubmit={submit} className="mt-6 space-y-5" data-testid="public-form">
          {form.template.map((f) => (
            <div key={f.name}>
              <label className="text-sm font-semibold text-moneygreen-800">
                {f[lang]} {f.required && <span className="text-destructive">*</span>}
              </label>
              <div className="mt-1.5">
                {f.type === "textarea" ? (
                  <textarea required={f.required} rows={3} data-testid={`pf-${f.name}`}
                    value={values[f.name] || ""} onChange={(e) => set(f.name, e.target.value)}
                    className="w-full px-3 py-2 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm" />
                ) : f.type === "select" ? (
                  <select required={f.required} data-testid={`pf-${f.name}`}
                    value={values[f.name] || ""} onChange={(e) => set(f.name, e.target.value)}
                    className="w-full px-3 py-2 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm">
                    <option value="">—</option>
                    {f.options.map((o) => <option key={o.value} value={o.value}>{o[lang]}</option>)}
                  </select>
                ) : f.type === "checkbox" ? (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" required={f.required} data-testid={`pf-${f.name}`}
                      checked={!!values[f.name]} onChange={(e) => set(f.name, e.target.checked)}
                      className="w-4 h-4 accent-moneygreen-600" />
                    <span className="text-sm text-stone-600">{t("iAgree")}</span>
                  </label>
                ) : f.type === "signature" ? (
                  <SignaturePad value={values[f.name]} onChange={(v) => set(f.name, v)} testid={`pf-${f.name}`} />
                ) : (
                  <input type={f.type === "date" ? "date" : "text"} required={f.required} data-testid={`pf-${f.name}`}
                    value={values[f.name] || ""} onChange={(e) => set(f.name, e.target.value)}
                    className="w-full px-3 py-2 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm" />
                )}
              </div>
            </div>
          ))}
          <button type="submit" disabled={submitting} data-testid="public-form-submit"
            className="w-full py-2.5 rounded-md bg-moneygreen-600 text-white font-semibold hover:bg-moneygreen-700 transition-colors duration-200 flex items-center justify-center gap-2 disabled:opacity-60">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}{t("submitForm")}
          </button>
        </form>
      </div>
    </Shell>
  );
}
