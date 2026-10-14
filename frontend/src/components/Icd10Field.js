import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import api from "../lib/api";

// Shared, page-lifetime cache of code -> "CODE — Description" labels, so a
// code already resolved once (by the picker, a label, or a table row) is
// never looked up twice. This never reads or writes any patient record —
// it only caches the result of GET /icd10/describe.
const labelCache = new Map();

async function resolveLabel(code) {
  const c = (code || "").trim();
  if (!c) return "";
  if (labelCache.has(c)) return labelCache.get(c);
  try {
    const r = await api.get("/icd10/describe", { params: { code: c } });
    const label = r.data?.label || c;
    labelCache.set(c, label);
    return label;
  } catch {
    return c; // lookup unreachable — show the bare code rather than nothing
  }
}

// Read-only display: "F43.10 — Post-traumatic stress disorder, unspecified".
// Shows the bare code immediately, then upgrades to the full label once
// resolved. An unrecognized or legacy code just stays as the bare code —
// nothing about the stored diagnosis changes.
export function Icd10Label({ code, className, emptyText = "—" }) {
  const c = (code || "").trim();
  const [label, setLabel] = useState(() => labelCache.get(c) || c);

  useEffect(() => {
    if (!c) { setLabel(""); return; }
    setLabel(labelCache.get(c) || c);
    if (labelCache.has(c)) return;
    let alive = true;
    resolveLabel(c).then((l) => { if (alive) setLabel(l); });
    return () => { alive = false; };
  }, [c]);

  if (!c) return <span className={className}>{emptyText}</span>;
  return <span className={className} data-testid="icd10-label">{label}</span>;
}

// Compact display: shows the bare code (for dense tables that don't have
// room for the full description) with the resolved description available
// as a hover tooltip, so the full text is still one hover away.
export function Icd10CodeTip({ code, className }) {
  const c = (code || "").trim();
  const [title, setTitle] = useState(() => labelCache.get(c) || "");
  useEffect(() => {
    if (!c) return;
    if (labelCache.has(c)) { setTitle(labelCache.get(c)); return; }
    let alive = true;
    resolveLabel(c).then((l) => { if (alive) setTitle(l); });
    return () => { alive = false; };
  }, [c]);
  if (!c) return null;
  return <span className={className} title={title !== c ? title : undefined}>{c}</span>;
}

// Editable diagnosis field: search ICD-10-CM codes by code or description
// as you type (debounced), pick a match from the dropdown. onChange always
// receives the bare code (e.g. "F43.10") — the "CODE — Description" text
// is display only, so the stored diagnosis field never changes shape.
// Typing a code directly still works even if the lookup service can't be
// reached, so this never blocks saving a note or invoice.
export function Icd10Picker({ value, onChange, placeholder, className = "", testId, t = (x) => x }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [rect, setRect] = useState(null);
  const wrapRef = useRef(null);
  const panelRef = useRef(null);
  const debounceRef = useRef(null);
  const resolvedFor = useRef({ code: "", label: "" });
  const editingRef = useRef(false);

  // Reflect external value changes (load/reset) as the resolved label,
  // unless the user is actively typing in this field right now.
  useEffect(() => {
    const code = (value || "").trim();
    if (editingRef.current) return;
    if (!code) { setQuery(""); resolvedFor.current = { code: "", label: "" }; return; }
    if (resolvedFor.current.code === code) { setQuery(resolvedFor.current.label); return; }
    setQuery(code);
    resolveLabel(code).then((label) => {
      resolvedFor.current = { code, label };
      if (!editingRef.current) setQuery(label);
    });
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (wrapRef.current && wrapRef.current.contains(e.target)) return;
      if (panelRef.current && panelRef.current.contains(e.target)) return;
      setOpen(false);
      editingRef.current = false;
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const measure = () => { if (wrapRef.current) setRect(wrapRef.current.getBoundingClientRect()); };

  const runSearch = (term) => {
    clearTimeout(debounceRef.current);
    const q = term.trim();
    if (q.length < 2) { setResults([]); setLoading(false); return; }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const r = await api.get("/icd10/search", { params: { q } });
        setResults(r.data?.results || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  };

  const onInput = (e) => {
    const v = e.target.value;
    editingRef.current = true;
    setQuery(v);
    measure();
    setOpen(true);
    runSearch(v);
    onChange && onChange(v); // raw text stays the value until a result is picked
  };

  const pick = (item) => {
    resolvedFor.current = { code: item.code, label: item.label };
    editingRef.current = false;
    setQuery(item.label);
    setOpen(false);
    onChange && onChange(item.code);
  };

  return (
    <div className="relative" ref={wrapRef}>
      <input
        value={query}
        onChange={onInput}
        onFocus={() => { measure(); editingRef.current = true; if (query.trim().length >= 2) { setOpen(true); runSearch(query); } }}
        onBlur={() => { editingRef.current = false; }}
        placeholder={placeholder}
        className={className}
        data-testid={testId}
        autoComplete="off"
      />
      {open && rect && (results.length > 0 || loading) && createPortal(
        <div ref={panelRef}
          style={{ position: "fixed", top: rect.bottom + 4, left: rect.left, width: Math.max(rect.width, 300), zIndex: 9999 }}
          className="max-h-60 overflow-auto rounded-md border border-border bg-white shadow-xl py-1 text-sm"
          data-testid={testId ? `${testId}-panel` : undefined}
        >
          {loading && <div className="px-3 py-2 text-stone-400">{t("searching") || "Searching…"}</div>}
          {!loading && results.map((r) => (
            <div key={r.code} onClick={() => pick(r)}
              data-testid={testId ? `${testId}-opt-${r.code}` : undefined}
              className="px-3 py-1.5 cursor-pointer hover:bg-tan-50 text-stone-700">
              <span className="font-semibold text-moneygreen-700">{r.code}</span>
              <span className="text-stone-500"> — {r.description}</span>
            </div>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}
