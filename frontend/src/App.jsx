import { useEffect } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import Ticker from "./components/Ticker";
import DockNav from "./components/DockNav";
import CursorDot from "./components/CursorDot";
import Footer from "./components/Footer";
import ProtectedRoute from "./components/ProtectedRoute";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import Diagnosis from "./pages/Diagnosis";
import Explorer from "./pages/Explorer";
import Audit from "./pages/Audit";
import Login from "./pages/Login";
import Register from "./pages/Register";
import RequestAccess from "./pages/RequestAccess";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Team from "./pages/Team";

function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) return; // let anchor links handle their own scroll
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname, hash]);
  return null;
}

export default function App() {
  const { pathname } = useLocation();
  const AUTH_PAGES = ["/login", "/register", "/request-access", "/forgot-password", "/reset-password"];
  const isAuthPage = AUTH_PAGES.includes(pathname);

  return (
    <>
      <ScrollManager />
      <CursorDot />
      {pathname === "/" && <Ticker />}
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/request-access" element={<RequestAccess />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/diagnosis"
          element={
            <ProtectedRoute>
              <Diagnosis />
            </ProtectedRoute>
          }
        />
        <Route
          path="/explorer"
          element={
            <ProtectedRoute>
              <Explorer />
            </ProtectedRoute>
          }
        />
        <Route
          path="/audit"
          element={
            <ProtectedRoute>
              <Audit />
            </ProtectedRoute>
          }
        />
        <Route
          path="/team"
          element={
            <ProtectedRoute>
              <Team />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Landing />} />
      </Routes>
      {!isAuthPage && <Footer />}
      {!isAuthPage && <DockNav />}
    </>
  );
}
