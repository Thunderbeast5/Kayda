import { useState, useEffect } from "react";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";
import EvidenceAnalyzerPage from "./pages/EvidenceAnalyzerPage";
import LexiGraphCypherPage from "./pages/LexiGraphCypherPage";
import LexiGraphAgentPage from "./pages/LexiGraphAgentPage";

export default function App() {
  const [page, setPage] = useState(getPageFromHash());

  useEffect(() => {
    const onHashChange = () => setPage(getPageFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return (
    <AuthProvider>
      <AppRouter page={page} />
    </AuthProvider>
  );
}

function AppRouter({ page }) {
  // ── Auth page (public) ────────────────────────────────────────────────────
  if (page === "auth" || page === "login" || page === "register") {
    return <AuthPage />;
  }

  // ── Protected routes ──────────────────────────────────────────────────────
  if (page === "evidence-analyzer") {
    return (
      <ProtectedRoute>
        <EvidenceAnalyzerPage
          onBack={() => { window.location.hash = "#/"; }}
        />
      </ProtectedRoute>
    );
  }

  if (page === "lexigraph-agent" || page === "lexigraph_agent") {
    return (
      <ProtectedRoute>
        <LexiGraphAgentPage
          onBack={() => { window.location.hash = "#/"; }}
          onSwitchToCypher={() => { window.location.hash = "#/text2cypher"; }}
        />
      </ProtectedRoute>
    );
  }

  if (page === "text2cypher" || page === "lexigraph" || page === "cypher") {
    return (
      <ProtectedRoute>
        <LexiGraphCypherPage
          onBack={() => { window.location.hash = "#/"; }}
        />
      </ProtectedRoute>
    );
  }

  // ── Default: home (protected) ─────────────────────────────────────────────
  return (
    <ProtectedRoute>
      <HomePage />
    </ProtectedRoute>
  );
}

function getPageFromHash() {
  const hash = window.location.hash.replace("#/", "").replace("#", "");
  return hash || "home";
}
