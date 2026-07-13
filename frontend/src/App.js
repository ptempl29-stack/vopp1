import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LanguageProvider } from "./context/LanguageContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Patients from "./pages/Patients";
import Appointments from "./pages/Appointments";
import Telehealth from "./pages/Telehealth";
import Notes from "./pages/Notes";
import Invoices from "./pages/Invoices";
import CptCodes from "./pages/CptCodes";
import Forms from "./pages/Forms";
import Messages from "./pages/Messages";
import PublicForm from "./pages/PublicForm";
import BillingReports from "./pages/BillingReports";
import Team from "./pages/Team";
import AcceptInvite from "./pages/AcceptInvite";
import AIAssistant from "./pages/AIAssistant";
import AuditLog from "./pages/AuditLog";
import Claims from "./pages/Claims";
import ChangePassword from "./pages/ChangePassword";
import { Loader2 } from "lucide-react";

function Protected({ children, tab }) {
  const { user, loading } = useAuth();
  if (loading)
    return <div className="min-h-screen flex items-center justify-center bg-tan-100"><Loader2 className="w-8 h-8 animate-spin text-moneygreen-600" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <ChangePassword />;
  if (tab && user.allowed_tabs && !user.allowed_tabs.includes(tab))
    return <Layout><div className="py-20 text-center text-stone-500" data-testid="no-access">You don't have access to this section.</div></Layout>;
  return <Layout>{children}</Layout>;
}

function App() {
  return (
    <div className="App">
      <LanguageProvider>
        <AuthProvider>
          <Toaster position="top-right" richColors />
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/form/:token" element={<PublicForm />} />
              <Route path="/accept-invite/:token" element={<AcceptInvite />} />
              <Route path="/" element={<Protected tab="dashboard"><Dashboard /></Protected>} />
              <Route path="/patients" element={<Protected tab="patients"><Patients /></Protected>} />
              <Route path="/appointments" element={<Protected tab="appointments"><Appointments /></Protected>} />
              <Route path="/telehealth" element={<Protected tab="telehealth"><Telehealth /></Protected>} />
              <Route path="/notes" element={<Protected tab="notes"><Notes /></Protected>} />
              <Route path="/invoices" element={<Protected tab="invoices"><Invoices /></Protected>} />
              <Route path="/cpt-codes" element={<Protected tab="cpt"><CptCodes /></Protected>} />
              <Route path="/reports" element={<Protected tab="reports"><BillingReports /></Protected>} />
              <Route path="/forms" element={<Protected tab="forms"><Forms /></Protected>} />
              <Route path="/messages" element={<Protected tab="messages"><Messages /></Protected>} />
              <Route path="/assistant" element={<Protected tab="assistant"><AIAssistant /></Protected>} />
              <Route path="/team" element={<Protected tab="team"><Team /></Protected>} />
              <Route path="/settings" element={<Protected tab="team"><Team /></Protected>} />
              <Route path="/audit" element={<Protected tab="audit"><AuditLog /></Protected>} />
              <Route path="/claims" element={<Protected tab="claims"><Claims /></Protected>} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </LanguageProvider>
    </div>
  );
}

export default App;
