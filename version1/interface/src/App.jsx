import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";
import EvidenceAnalyzerPage from "./pages/EvidenceAnalyzerPage";
import LexiGraphCypherPage from "./pages/LexiGraphCypherPage";
import LexiGraphAgentPage from "./pages/LexiGraphAgentPage";
import ProfilePage from "./pages/ProfilePage";
import MultiplayerMode from "./pages/MultiplayerMode";
import KaydaPricingPage from "./pages/PricingPage";

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
          <Route path="/pricing" element={<KaydaPricingPage />} />

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
            path="/lexigraph"
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
            path="/multiplayer"
            element={
              <ProtectedRoute>
                <MultiplayerMode />
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
