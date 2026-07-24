import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { usePrivacy } from "../context/PrivacyContext";
import {
  LayoutDashboard, Users, CalendarDays, FileText, ReceiptText,
  ClipboardList, MessageSquare, Video, LogOut, Menu, Stethoscope, Languages, Hash,
  BarChart3, UserCog, ShieldCheck, FolderArchive, Settings, Sparkles, Eye, EyeOff, FolderTree, Mail, DollarSign,
} from "lucide-react";

const nav = [
  { to: "/", tab: "dashboard", key: "dashboard", icon: LayoutDashboard, end: true },
  { to: "/patients", tab: "patients", key: "patients", icon: Users },
  { to: "/appointments", tab: "appointments", key: "appointments", icon: CalendarDays },
  { to: "/telehealth", tab: "telehealth", key: "telehealth", icon: Video },
  { to: "/notes", tab: "notes", key: "notes", icon: FileText },
  { to: "/invoices", tab: "invoices", key: "invoices", icon: ReceiptText },
  { to: "/cpt-codes", tab: "cpt", key: "cptCodes", icon: Hash },
  { to: "/reports", tab: "reports", key: "reports", icon: BarChart3 },
  { to: "/forms", tab: "forms", key: "forms", icon: ClipboardList },
  { to: "/folders", tab: "folders", key: "patientFolders", icon: FolderTree },
  { to: "/claims", tab: "claims", key: "claims", icon: FolderArchive },
  { to: "/mailbox", tab: "mailbox", key: "mailbox", icon: Mail },
  { to: "/messages", tab: "messages", key: "messages", icon: MessageSquare },
  { to: "/assistant", tab: "assistant", key: "aiAssistant", icon: Sparkles },
  { to: "/settings", tab: "team", key: "settings", icon: Settings },
  { to: "/audit", tab: "audit", key: "auditLog", icon: ShieldCheck },
];

const roleColors = {
  doctor: "bg-moneygreen-600", nurse: "bg-moneygreen-500", psychologist: "bg-moneygreen-400",
  receptionist: "bg-tan-400", biller: "bg-stone-500", admin: "bg-moneygreen-700",
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const { t, lang, toggle } = useLang();
  const { privacy, toggle: togglePrivacy } = usePrivacy();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <div className="min-h-screen flex bg-tan-100">
      {/* Sidebar */}
      <aside className={`fixed lg:static z-40 h-full w-64 bg-moneygreen-800 text-tan-100 flex flex-col transition-transform duration-200 ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="px-5 py-6 border-b border-moneygreen-700">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-md bg-moneygreen-500 flex items-center justify-center">
              <Stethoscope className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="font-heading font-extrabold text-sm leading-tight text-white">Veterans of<br/>Puerto Plata</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 custom-scroll overflow-y-auto">
          {nav.filter((item) => (user?.allowed_tabs || ["dashboard"]).includes(item.tab)).map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}
              onClick={() => setOpen(false)}
              data-testid={`nav-${item.key}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-200 ${
                  isActive ? "bg-moneygreen-600 text-white" : "text-tan-200 hover:bg-moneygreen-700 hover:text-white"
                }`}>
              <item.icon className="w-[18px] h-[18px]" />
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-moneygreen-700">
          <div className="flex items-center gap-3 mb-3">
            <div className={`w-9 h-9 rounded-full flex items-center justify-center text-white font-heading font-bold text-sm ${roleColors[user?.role] || "bg-moneygreen-500"}`}>
              {user?.name?.[0] || "U"}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white truncate">{user?.name}</p>
              <p className="text-xs text-tan-300 capitalize">{user?.role === "admin" ? "CEO" : user?.role}</p>
            </div>
          </div>
          <button onClick={handleLogout} data-testid="logout-btn"
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-tan-200 hover:bg-moneygreen-700 hover:text-white transition-colors duration-200">
            <LogOut className="w-4 h-4" /> {t("logout")}
          </button>
        </div>
      </aside>

      {open && <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setOpen(false)} />}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-white border-b border-border flex items-center justify-between px-4 lg:px-8 sticky top-0 z-20">
          <button className="lg:hidden text-moneygreen-700" onClick={() => setOpen(true)} data-testid="menu-btn">
            <Menu className="w-6 h-6" />
          </button>
          <div className="hidden lg:block">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">{t("tagline")}</p>
          </div>
          <div className="flex items-center gap-2">
            {(user?.role === "admin" || (user?.allowed_tabs || []).includes("claims")) && (
              <button onClick={() => navigate("/claim-builder")} data-testid="claim-automation-btn"
                title={t("claimBuilder")}
                className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-moneygreen-600 text-white border border-moneygreen-600 text-sm font-semibold hover:bg-moneygreen-700 transition-colors duration-200 shadow-sm">
                <DollarSign className="w-4 h-4" />
                <span className="hidden sm:inline">{t("claimBuilder")}</span>
              </button>
            )}
            <button onClick={togglePrivacy} data-testid="privacy-toggle"
              title={t("privacyMode")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md border text-sm font-semibold transition-colors duration-200 ${
                privacy ? "bg-moneygreen-600 text-white border-moneygreen-600" : "border-border text-moneygreen-700 hover:bg-moneygreen-50"
              }`}>
              {privacy ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              <span className="hidden sm:inline">{t("privacyMode")}</span>
            </button>
            <button onClick={toggle} data-testid="lang-toggle"
              className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border text-sm font-semibold text-moneygreen-700 hover:bg-moneygreen-50 transition-colors duration-200">
              <Languages className="w-4 h-4" />
              {lang === "en" ? "ES" : "EN"}
            </button>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-8 custom-scroll overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
