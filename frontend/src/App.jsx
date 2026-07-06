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
  const isAuthPage = pathname === "/login" || pathname === "/register";

  return (
    <>
      <ScrollManager />
      <CursorDot />
      {pathname === "/" && <Ticker />}
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
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
        <Route path="*" element={<Landing />} />
      </Routes>
      {!isAuthPage && <Footer />}
      {!isAuthPage && <DockNav />}
    </>
  );
}
