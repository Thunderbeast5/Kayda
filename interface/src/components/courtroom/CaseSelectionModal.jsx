import { useState, useEffect } from "react";
import { X, FolderOpen, Scale, BookOpen, Clock, Check, AlertCircle, RefreshCw } from "lucide-react";

export default function CaseSelectionModal({ isOpen, onClose, onSelectCase, currentCaseId }) {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchCases = async () => {
    setLoading(true);
    setError(null);
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
      const res = await fetch(`${apiUrl}/api/cases`);
      if (!res.ok) {
        throw new Error(`Server status ${res.status}`);
      }
      const data = await res.json();
      setCases(data);
    } catch (err) {
      console.error("Failed to load case bank:", err);
      setError("Unable to connect to backend case bank. Make sure backend is running.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchCases();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
      <div className="bg-white border border-[#D4AF37]/40 rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Modal Header */}
        <div className="bg-[#2C1810] text-[#FAF8F5] px-6 py-4 flex items-center justify-between border-b border-[#D4AF37]/30">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-[#D4AF37]/20 text-[#D4AF37]">
              <FolderOpen size={20} />
            </div>
            <div>
              <h2 className="font-heading font-bold text-lg leading-tight">Case Selection Bank</h2>
              <p className="text-[11px] font-mono uppercase tracking-wider text-[#D4AF37]/80">
                Observer Mode // Landmark Cases
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#FAF8F5]/70 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {loading && (
            <div className="py-12 flex flex-col items-center justify-center text-center">
              <div className="w-10 h-10 border-3 border-[#D4AF37]/30 border-t-[#D4AF37] rounded-full animate-spin mb-4" />
              <p className="font-heading font-semibold text-sm text-[#2C1810]">
                Fetching Available Cases...
              </p>
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start justify-between gap-3 text-red-800">
              <div className="flex items-start gap-2.5">
                <AlertCircle size={18} className="text-red-600 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-bold">Failed to load case bank</p>
                  <p className="mt-0.5 text-red-700">{error}</p>
                </div>
              </div>
              <button
                onClick={fetchCases}
                className="flex items-center gap-1 text-[11px] font-bold text-red-800 hover:underline shrink-0"
              >
                <RefreshCw size={12} /> Retry
              </button>
            </div>
          )}

          {!loading && !error && cases.length === 0 && (
            <div className="py-10 text-center text-[#5D4037]">
              <p className="font-semibold text-sm">No cases found in observer storage.</p>
            </div>
          )}

          {!loading && !error && cases.map((c) => {
            const isSelected = String(currentCaseId) === String(c.id);
            return (
              <div
                key={c.id}
                onClick={() => {
                  onSelectCase(c.id);
                  onClose();
                }}
                className={`p-5 rounded-xl border transition-all duration-200 cursor-pointer group relative ${
                  isSelected
                    ? "bg-[#FAF8F5] border-[#D4AF37] shadow-md ring-1 ring-[#D4AF37]"
                    : "bg-white border-[#2C1810]/15 hover:border-[#D4AF37]/80 hover:shadow-md hover:-translate-y-[1px]"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-[#2C1810] text-[#FAF8F5]">
                        Case #{c.id}
                      </span>
                      {c.court && (
                        <span className="font-mono text-[10px] text-[#8C5A3C] font-semibold flex items-center gap-1">
                          <Scale size={11} /> {c.court}
                        </span>
                      )}
                    </div>

                    <h3 className="font-heading font-bold text-base text-[#2C1810] group-hover:text-[#8C5A3C] transition-colors">
                      {c.title}
                    </h3>

                    {c.summary && (
                      <p className="text-xs text-[#5D4037] leading-relaxed line-clamp-2">
                        {c.summary}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-4 pt-2 text-[11px] font-mono text-[#8C5A3C]">
                      {c.decided_on && (
                        <span className="flex items-center gap-1">
                          <Clock size={12} /> Decided: {c.decided_on}
                        </span>
                      )}
                      {c.primary_charge && (
                        <span className="flex items-center gap-1 font-bold text-[#2C1810]/80">
                          <BookOpen size={12} /> {c.primary_charge}
                        </span>
                      )}
                    </div>
                  </div>

                  {isSelected ? (
                    <div className="p-2 rounded-full bg-[#D4AF37] text-white shrink-0">
                      <Check size={16} strokeWidth={3} />
                    </div>
                  ) : (
                    <button className="px-4 py-1.5 text-[11px] font-bold uppercase tracking-wider text-[#FAF8F5] bg-[#2C1810] rounded-md group-hover:bg-[#8C5A3C] transition-colors shrink-0">
                      Select Case
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Modal Footer */}
        <div className="bg-[#FAF8F5] px-6 py-3 border-t border-[#2C1810]/10 flex items-center justify-between text-xs text-[#5D4037]">
          <span>Click a case to load its full briefing and playback simulation.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-semibold text-[#2C1810] hover:underline cursor-pointer"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
