import React, { createContext, useContext, useState } from "react";

const PrivacyContext = createContext();

export function PrivacyProvider({ children }) {
  const [privacy, setPrivacy] = useState(false);
  const toggle = () => setPrivacy((p) => !p);
  return (
    <PrivacyContext.Provider value={{ privacy, toggle }}>
      {children}
    </PrivacyContext.Provider>
  );
}

export const usePrivacy = () => useContext(PrivacyContext);

// Masks sensitive patient data (name / SSN / DOB) when privacy mode is on.
// Click to reveal, click again to hide.
export function Private({ value, className = "" }) {
  const { privacy } = usePrivacy();
  const [revealed, setRevealed] = useState(false);

  if (!privacy || !value) return <span className={className}>{value || "—"}</span>;

  return (
    <span
      role="button"
      tabIndex={0}
      data-testid="private-value"
      onClick={(e) => { e.stopPropagation(); setRevealed((r) => !r); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setRevealed((r) => !r); } }}
      title={revealed ? "Click to hide" : "Click to reveal"}
      className={`cursor-pointer select-none rounded px-1 transition-colors duration-150 ${
        revealed ? "bg-amber-100 text-stone-900" : "bg-stone-700 text-stone-700 hover:bg-stone-600"
      } ${className}`}>
      {value}
    </span>
  );
}
