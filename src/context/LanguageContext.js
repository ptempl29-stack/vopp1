import React, { createContext, useContext, useState } from "react";
import { translations } from "../i18n";

const LanguageContext = createContext();

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(localStorage.getItem("vpp_lang") || "en");
  const toggle = () => {
    const next = lang === "en" ? "es" : "en";
    setLang(next);
    localStorage.setItem("vpp_lang", next);
  };
  const t = (key) => translations[lang][key] || key;
  return (
    <LanguageContext.Provider value={{ lang, toggle, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLang = () => useContext(LanguageContext);
