import { ChevronRight, RotateCcw, Gavel, Play, Pause } from "lucide-react";

export default function ObserverControlBar({
  currentIndex,
  totalTurns,
  onNext,
  onRestart,
  isAutoPlaying = false,
  onToggleAutoPlay,
}) {
  const isConcluded = totalTurns > 0 && currentIndex >= totalTurns;
  const isEmpty = totalTurns === 0;

  return (
    <div className="bg-white/80 backdrop-blur-md border-t border-[#2C1810]/10 px-4 py-3 z-30 flex flex-col items-center justify-center w-full shadow-md">
      <div className="mb-2 text-center flex items-center justify-center gap-3">
        <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-primaryBrown/80 flex items-center justify-center gap-1.5">
          {isEmpty
            ? "Loading transcript..."
            : isConcluded
            ? "Proceedings concluded"
            : `Turn ${currentIndex + 1} of ${totalTurns}`}
        </span>
        {isAutoPlaying && (
          <span className="inline-flex items-center gap-1 text-[9px] font-mono font-bold uppercase tracking-widest text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-300 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-ping" /> Auto-Playing
          </span>
        )}
      </div>

      <div className="w-full max-w-3xl flex items-center justify-center gap-3">
        {/* Restart */}
        <button
          type="button"
          onClick={onRestart}
          disabled={isEmpty || currentIndex === 0}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[11px] font-bold uppercase tracking-widest border transition-all cursor-pointer ${
            isEmpty || currentIndex === 0
              ? "border-transparent text-gray-300 cursor-not-allowed"
              : "border-[#2C1810]/20 text-[#2C1810] hover:bg-[#FAF8F5]"
          }`}
          title="Restart from beginning"
        >
          <RotateCcw size={13} /> Restart
        </button>

        {/* Auto Play / Pause Toggle */}
        {onToggleAutoPlay && (
          <button
            type="button"
            onClick={onToggleAutoPlay}
            disabled={isEmpty || isConcluded}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-[11px] font-bold uppercase tracking-widest border transition-all cursor-pointer ${
              isEmpty || isConcluded
                ? "border-transparent text-gray-300 cursor-not-allowed"
                : isAutoPlaying
                ? "bg-amber-100 text-amber-900 border-amber-300 hover:bg-amber-200"
                : "border-[#D4AF37] text-[#2C1810] hover:bg-[#FAF8F5]"
            }`}
            title={isAutoPlaying ? "Pause Auto-Play" : "Auto-Play all turns with natural pacing"}
          >
            {isAutoPlaying ? <Pause size={13} /> : <Play size={13} />}
            {isAutoPlaying ? "Pause" : "Auto-Play"}
          </button>
        )}

        {/* Next Step */}
        <button
          type="button"
          onClick={onNext}
          disabled={isEmpty || isConcluded}
          className={`flex items-center gap-2 px-6 py-2 rounded-full text-[12px] font-bold uppercase tracking-widest border transition-all shadow-sm ${
            isEmpty || isConcluded
              ? "bg-gray-100 text-gray-400 border-transparent cursor-not-allowed"
              : "bg-[#2C1810] text-[#C5A059] border-[#C5A059] hover:bg-[#3D2318] hover:scale-105 cursor-pointer"
          }`}
        >
          {isConcluded ? <Gavel size={14} /> : <ChevronRight size={14} />}
          {isConcluded ? "Verdict Delivered" : "Next Turn"}
        </button>
      </div>
    </div>
  );
}