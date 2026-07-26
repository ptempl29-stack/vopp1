import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Trash2, RotateCcw, EyeOff } from "lucide-react";
import { useHiddenOptions } from "../context/HiddenOptionsContext";
import { useLang } from "../context/LanguageContext";

function labelOf(ch) {
  if (ch == null) return "";
  if (Array.isArray(ch)) return ch.map((x) => (x == null || typeof x === "object" ? "" : String(x))).join("");
  return typeof ch === "object" ? "" : String(ch);
}

export function ManagedSelect({ listKey, value, onChange, children, className = "", disabled, required, ...rest }) {
  const { map, hide, restore } = useHiddenOptions();
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [rect, setRect] = useState(null);
  const btnRef = useRef(null);
  const panelRef = useRef(null);
  const testid = rest["data-testid"];

  const measure = () => { if (btnRef.current) setRect(btnRef.current.getBoundingClientRect()); };
  useLayoutEffect(() => { if (open) measure(); }, [open]);
  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (btnRef.current && btnRef.current.contains(e.target)) return;
      if (panelRef.current && panelRef.current.contains(e.target)) return;
      setOpen(false);
    };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  const opts = React.Children.toArray(children)
    .filter((c) => c && c.type === "option")
    .map((c) => ({ value: c.props.value == null ? "" : String(c.props.value), label: labelOf(c.props.children), disabled: !!c.props.disabled }));

  const hiddenList = map[String(listKey).replace(/\./g, "_")] || [];
  const visible = opts.filter((o) => o.value === "" || !hiddenList.includes(o.value));
  const hiddenOpts = opts.filter((o) => o.value !== "" && hiddenList.includes(o.value));
  const cur = opts.find((o) => o.value === String(value == null ? "" : value));
  const isPlaceholder = !cur || cur.value === "";

  const pick = (v) => { onChange && onChange({ target: { value: v } }); setOpen(false); };

  return (
    <div className="relative">
      <button type="button" ref={btnRef} disabled={disabled} data-testid={testid}
        onClick={() => !disabled && setOpen((o) => !o)}
        className={`${className} text-left flex items-center justify-between gap-2 ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}>
        <span className={`truncate ${isPlaceholder ? "text-stone-400" : ""}`}>{cur ? cur.label : ""}</span>
        <ChevronDown className="w-4 h-4 shrink-0 text-stone-400" />
      </button>
      {required && (
        <input tabIndex={-1} aria-hidden="true" required value={value || ""} onChange={() => {}}
          style={{ position: "absolute", left: 12, bottom: 0, height: 0, width: 1, opacity: 0, pointerEvents: "none" }} />
      )}
      {open && rect && createPortal(
        <div ref={panelRef} data-testid={testid ? `${testid}-panel` : undefined}
          style={{ position: "fixed", top: rect.bottom + 4, left: rect.left, width: rect.width, zIndex: 9999 }}
          className="max-h-64 overflow-auto rounded-md border border-border bg-white shadow-xl py-1">
          {visible.map((o) => (
            <div key={o.value || "__empty"} onClick={() => !o.disabled && pick(o.value)}
              data-testid={testid && o.value ? `${testid}-opt-${o.value}` : undefined}
              className={`group flex items-center justify-between gap-2 px-3 py-1.5 cursor-pointer hover:bg-tan-50 ${o.disabled ? "opacity-50" : ""}`}>
              <span className={`truncate text-sm ${o.value === String(value == null ? "" : value) && o.value ? "font-semibold text-moneygreen-700" : "text-stone-700"}`}>{o.label}</span>
              {o.value !== "" && (
                <button type="button" title={t("hideFromList")} data-testid={testid ? `${testid}-hide-${o.value}` : undefined}
                  onClick={(e) => { e.stopPropagation(); hide(listKey, o.value); if (String(value == null ? "" : value) === o.value) onChange && onChange({ target: { value: "" } }); }}
                  className="opacity-0 group-hover:opacity-100 text-stone-400 hover:text-red-500 transition-opacity shrink-0">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
          {visible.filter((o) => o.value !== "").length === 0 && (
            <div className="px-3 py-2 text-xs text-stone-400">{t("noOptions")}</div>
          )}
          {hiddenOpts.length > 0 && (
            <div className="border-t border-border mt-1 pt-1">
              <button type="button" onClick={() => setShowHidden((s) => !s)}
                data-testid={testid ? `${testid}-toggle-hidden` : undefined}
                className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-stone-500 hover:text-moneygreen-700">
                <EyeOff className="w-3.5 h-3.5" />{showHidden ? t("hideRemoved") : `${hiddenOpts.length} ${t("removedFromList")}`}
              </button>
              {showHidden && hiddenOpts.map((o) => (
                <div key={o.value} className="flex items-center justify-between gap-2 px-3 py-1.5">
                  <span className="truncate text-sm text-stone-400 line-through">{o.label}</span>
                  <button type="button" title={t("restore")} data-testid={testid ? `${testid}-restore-${o.value}` : undefined}
                    onClick={() => restore(listKey, o.value)} className="text-stone-400 hover:text-moneygreen-600 shrink-0">
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>,
        document.body
      )}
    </div>
  );
}
