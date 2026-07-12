import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Card } from "../components/ui-kit";
import {
  Users, CalendarClock, ReceiptText, ClipboardList, MessageSquare, FileText, CalendarDays,
} from "lucide-react";

export default function Dashboard() {
  const { user } = useAuth();
  const { t } = useLang();
  const [stats, setStats] = useState(null);

  useEffect(() => { api.get("/stats").then((r) => setStats(r.data)).catch(() => {}); }, []);

  const cards = [
    { key: "totalPatients", value: stats?.patients, icon: Users, tone: "moneygreen-600" },
    { key: "apptToday", value: stats?.appointments_today, icon: CalendarClock, tone: "moneygreen-500" },
    { key: "totalAppointments", value: stats?.appointments_total, icon: CalendarDays, tone: "tan-400" },
    { key: "unpaidInvoices", value: stats?.unpaid_invoices, icon: ReceiptText, tone: "stone-500" },
    { key: "pendingNotes", value: stats?.pending_notes, icon: FileText, tone: "moneygreen-600" },
    { key: "pendingForms", value: stats?.pending_forms, icon: ClipboardList, tone: "tan-400" },
    { key: "unreadMessages", value: stats?.unread_messages, icon: MessageSquare, tone: "moneygreen-500" },
  ];

  return (
    <div>
      <div className="mb-8">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">{t("dashboard")}</p>
        <h1 className="font-heading text-3xl sm:text-4xl font-extrabold text-moneygreen-800 tracking-tight mt-1">
          {t("goodDay")}, {user?.name}.
        </h1>
        <p className="text-stone-500 mt-2">{t("overview")}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c, i) => (
          <motion.div key={c.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}>
            <Card className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500">{t(c.key)}</p>
                  <p className="font-heading text-4xl font-extrabold text-moneygreen-800 mt-2">
                    {c.value ?? "—"}
                  </p>
                </div>
                <div className={`w-11 h-11 rounded-md bg-${c.tone} flex items-center justify-center`}>
                  <c.icon className="w-5 h-5 text-white" />
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 p-6 overflow-hidden relative">
          <div className="relative z-10 max-w-md">
            <h3 className="font-heading text-2xl font-bold text-moneygreen-800">{t("appName")}</h3>
            <p className="text-stone-500 mt-2 leading-relaxed">
              {t("tagline")} — {t("overview")}
            </p>
          </div>
          <img src="https://images.unsplash.com/photo-1622253692010-333f2da6031d?crop=entropy&cs=srgb&fm=jpg&q=85&w=400"
            alt="clinician" className="absolute right-0 top-0 h-full w-1/3 object-cover opacity-90 hidden sm:block rounded-r-lg" />
        </Card>
        <Card className="p-6">
          <p className="text-xs font-bold uppercase tracking-[0.15em] text-stone-500 mb-3">{t("role")}</p>
          <p className="font-heading text-xl font-bold text-moneygreen-700 capitalize">{user?.role}</p>
          <p className="text-sm text-stone-500 mt-1">{user?.email}</p>
        </Card>
      </div>
    </div>
  );
}
