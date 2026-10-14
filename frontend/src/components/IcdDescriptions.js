import React from "react";

export const icdLines = (value, catalog, saved) => {
  const codes = String(value || "").split(/[,;\n]+/).map((c) => c.trim()).filter(Boolean);
  const lib = Object.fromEntries((catalog || []).map((c) => [String(c.code).trim().toUpperCase(), (c.description || "").trim()]));
  const kept = Object.fromEntries((saved || []).map((d) => [String(d.code).toUpperCase(), d.description || ""]));
  return codes.map((code) => ({ code, description: kept[code.toUpperCase()] || lib[code.toUpperCase()] || "" }));
};

export const IcdDescriptions = ({ value, catalog, saved, t, testPrefix = "inv" }) => {
  const lines = icdLines(value, catalog, saved);
  if (!lines.length) return null;
  return (
    <div className="mt-1.5 space-y-0.5" data-testid={`${testPrefix}-icd-descriptions`}>
      {lines.map(({ code, description }, i) => (
        <div key={`${code}-${i}`} className="text-xs leading-snug" data-testid={`${testPrefix}-icd-desc-${i}`}>
          <span className="font-mono font-semibold text-moneygreen-800">{code}</span>
          {description
            ? <span className="text-stone-600"> — {description}</span>
            : <span className="text-amber-700 no-print" data-testid={`${testPrefix}-icd-desc-missing-${i}`}> — {t("icdDescMissing")}</span>}
        </div>
      ))}
    </div>
  );
};
