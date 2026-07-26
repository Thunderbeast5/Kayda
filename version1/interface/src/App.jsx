import { useState, useEffect } from "react";
import HomePage from "./pages/HomePage";
import EvidenceAnalyzerPage from "./pages/EvidenceAnalyzerPage";
import LexiGraphCypherPage from "./pages/LexiGraphCypherPage";

export default function App() {
  const [page, setPage] = useState(getPageFromHash());

  useEffect(() => {
    const onHashChange = () => setPage(getPageFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  if (page === "evidence-analyzer") {
    return (
      <EvidenceAnalyzerPage
        onBack={() => {
          window.location.hash = "#/";
        }}
      />
    );
  }

  if (page === "text2cypher" || page === "lexigraph" || page === "cypher") {
    return (
      <LexiGraphCypherPage
        onBack={() => {
          window.location.hash = "#/";
        }}
      />
    );
  }

  return <HomePage />;
}

function getPageFromHash() {
  const hash = window.location.hash.replace("#/", "").replace("#", "");
  return hash || "home";
}

