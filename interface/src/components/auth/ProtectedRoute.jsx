import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import GavelLoader from "../GavelLoader";

export default function ProtectedRoute({ children }) {
  const { currentUser, loading } = useAuth();

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#FAF8F5]">
        <GavelLoader message="Verifying Your Authority to Appear" />
      </main>
    );
  }

  if (!currentUser) {
    return <Navigate to="/auth" replace />;
  }

  return children;
}
