import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";
import EvidenceAnalyzerPage from "./pages/EvidenceAnalyzerPage";
import LexiGraphCypherPage from "./pages/LexiGraphCypherPage";
import LexiGraphAgentPage from "./pages/LexiGraphAgentPage";
import ProfilePage from "./pages/ProfilePage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public routes */}
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/login" element={<Navigate to="/auth" replace />} />

          {/* Public landing page */}
          <Route path="/" element={<HomePage />} />

          {/* Protected routes */}
          <Route
            path="/evidence-analyzer"
            element={
              <ProtectedRoute>
                <EvidenceAnalyzerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/lexigraph-agent"
            element={
              <ProtectedRoute>
                <LexiGraphAgentPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/text2cypher"
            element={
              <ProtectedRoute>
                <LexiGraphCypherPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile/:userId"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
