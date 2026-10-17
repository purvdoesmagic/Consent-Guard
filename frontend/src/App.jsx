import { Link, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import { Loading } from "./components/Feedback.jsx";
import { useAuth } from "./hooks/useAuth.jsx";
import AccountPage from "./pages/AccountPage.jsx";
import AuditPage from "./pages/AuditPage.jsx";
import { LoginPage, MfaVerifyPage, RegisterPage } from "./pages/AuthPages.jsx";
import CaseDetailPage from "./pages/CaseDetailPage.jsx";
import CasesPage from "./pages/CasesPage.jsx";
import { ConsentCreatePage, ConsentDetailPage, ConsentsPage } from "./pages/ConsentPages.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DetectionPage from "./pages/DetectionPage.jsx";
import IntegrityPage from "./pages/IntegrityPage.jsx";
import RecordsPage from "./pages/RecordsPage.jsx";

// Route guards only shape navigation; every protected endpoint is authorized by the backend.
function RequireAuth({ roles, allowWithoutMfa = false, children }) {
  const { status, user } = useAuth();
  if (status === "loading") return <Loading label="Checking session…" />;
  if (status === "mfa") return <Navigate to="/mfa" replace />;
  if (status !== "authenticated") return <Navigate to="/login" replace />;
  // Investigators must enroll MFA first (also enforced server-side).
  if (user.role === "investigator" && !user.mfa_enabled && !allowWithoutMfa) {
    return <Navigate to="/account" replace />;
  }
  if (roles && !roles.includes(user.role)) return <NotFound />;
  return children;
}

function NotFound() {
  return (
    <div className="card empty">
      <strong>Page not found</strong>
      <p>The page does not exist or is not available for your role.</p>
      <Link to="/">Go to dashboard</Link>
    </div>
  );
}

export default function App() {
  const { status } = useAuth();
  if (status === "loading") return <Loading label="Loading ConsentGuard…" />;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/mfa" element={<MfaVerifyPage />} />
      <Route element={<RequireAuth allowWithoutMfa><Layout /></RequireAuth>}>
        <Route index element={<RequireAuth><DashboardPage /></RequireAuth>} />
        <Route path="consents" element={<RequireAuth><ConsentsPage /></RequireAuth>} />
        <Route path="consents/new" element={<RequireAuth roles={["subject"]}><ConsentCreatePage /></RequireAuth>} />
        <Route path="consents/:id" element={<RequireAuth><ConsentDetailPage /></RequireAuth>} />
        <Route path="records" element={<RequireAuth roles={["subject", "processor"]}><RecordsPage /></RequireAuth>} />
        <Route path="audit" element={<RequireAuth><AuditPage /></RequireAuth>} />
        <Route path="integrity" element={<RequireAuth><IntegrityPage /></RequireAuth>} />
        <Route path="cases" element={<RequireAuth roles={["investigator"]}><CasesPage /></RequireAuth>} />
        <Route path="cases/:id" element={<RequireAuth roles={["investigator"]}><CaseDetailPage /></RequireAuth>} />
        <Route path="detection" element={<RequireAuth roles={["investigator"]}><DetectionPage /></RequireAuth>} />
        <Route path="account" element={<RequireAuth allowWithoutMfa><AccountPage /></RequireAuth>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
