import { useAuth } from "../../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { currentUser, loading } = useAuth();

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#FAF9F7",
          gap: "20px",
        }}
      >
        {/* Spinning gavel / ring */}
        <div
          style={{
            width: "52px",
            height: "52px",
            borderRadius: "50%",
            border: "3px solid #D4AF37",
            borderTopColor: "#2C1810",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <p
          style={{
            fontFamily: "'Poppins', sans-serif",
            fontSize: "14px",
            color: "#8C5A3C",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontWeight: 600,
          }}
        >
          Verifying session…
        </p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!currentUser) {
    window.location.hash = "#/auth";
    return null;
  }

  return children;
}
