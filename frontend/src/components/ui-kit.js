import React from "react";
import { X, Inbox } from "lucide-react";

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="font-heading text-3xl font-extrabold text-moneygreen-800 tracking-tight">{title}</h1>
        {subtitle && <p className="text-stone-500 mt-1">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
        className={`bg-white rounded-lg shadow-xl w-full ${wide ? "max-w-3xl" : "max-w-lg"} max-h-[90vh] overflow-y-auto custom-scroll`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-white">
          <h3 className="font-heading text-lg font-bold text-moneygreen-800">{title}</h3>
          <button onClick={onClose} data-testid="modal-close" className="text-stone-500 hover:text-moneygreen-700 transition-colors duration-200">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <div>
      <label className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{label}</label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

export const inputCls =
  "w-full px-3 py-2 rounded-md bg-white border border-border focus:outline-none focus:ring-2 focus:ring-moneygreen-500 text-sm";

export function Btn({ children, variant = "primary", className = "", ...props }) {
  const styles = {
    primary: "bg-moneygreen-600 text-white hover:bg-moneygreen-700",
    outline: "bg-white border border-border text-moneygreen-700 hover:bg-moneygreen-50",
    ghost: "text-stone-500 hover:text-moneygreen-700 hover:bg-tan-100",
    danger: "bg-white border border-border text-destructive hover:bg-red-50",
  };
  return (
    <button {...props}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold transition-colors duration-200 disabled:opacity-60 ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Badge({ children, tone = "gray", ...props }) {
  const tones = {
    green: "bg-moneygreen-100 text-moneygreen-700",
    tan: "bg-tan-200 text-tan-900",
    red: "bg-red-100 text-red-700",
    amber: "bg-amber-100 text-amber-700",
    gray: "bg-stone-200 text-stone-600",
  };
  return <span {...props} className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold capitalize ${tones[tone]}`}>{children}</span>;
}

export function Empty({ text }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-stone-400">
      <Inbox className="w-10 h-10 mb-3" />
      <p className="text-sm">{text}</p>
    </div>
  );
}

export function Card({ children, className = "", ...props }) {
  return <div {...props} className={`bg-white rounded-lg border border-border ${className}`}>{children}</div>;
}
