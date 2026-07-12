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
import Forms from "./pages/Forms";
import Messages from "./pages/Messages";
import { Loader2 } from "lucide-react";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading)
    return <div className="min-h-screen flex items-center justify-center bg-tan-100"><Loader2 className="w-8 h-8 animate-spin text-moneygreen-600" /></div>;
  if (!user) return <Navigate to="/login" replace />;
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
              <Route path="/" element={<Protected><Dashboard /></Protected>} />
              <Route path="/patients" element={<Protected><Patients /></Protected>} />
              <Route path="/appointments" element={<Protected><Appointments /></Protected>} />
              <Route path="/telehealth" element={<Protected><Telehealth /></Protected>} />
              <Route path="/notes" element={<Protected><Notes /></Protected>} />
              <Route path="/invoices" element={<Protected><Invoices /></Protected>} />
              <Route path="/forms" element={<Protected><Forms /></Protected>} />
              <Route path="/messages" element={<Protected><Messages /></Protected>} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </LanguageProvider>
    </div>
  );
}

export default App;
