import { ChevronRight, RotateCcw, Gavel } from "lucide-react";

export default function ObserverControlBar({
  currentIndex,
  totalTurns,
  onNext,
  onRestart,
}) {
  const isConcluded = totalTurns > 0 && currentIndex >= totalTurns;
  const isEmpty = totalTurns === 0;

  return (
    <div className="bg-transparent px-4 py-4 z-30 flex flex-col items-center justify-center w-full">
      <div className="mb-2 text-center">
        <span className="text-[10px] font-bold uppercase tracking-widest text-primaryBrown/60 flex items-center justify-center gap-1.5">
          {isEmpty
            ? "Loading transcript..."
            : isConcluded
            ? "Proceedings concluded"
            : `Turn ${currentIndex + 1} of ${totalTurns}`}
        </span>
      </div>

      <div className="w-full max-w-3xl flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={onRestart}
          disabled={isEmpty || currentIndex === 0}
          className={`flex items-center gap-1.5 px-4 py-2.5 rounded-full text-[11px] font-bold uppercase tracking-widest border transition-all cursor-pointer ${
            isEmpty || currentIndex === 0
              ? "border-transparent text-gray-300 cursor-not-allowed"
              : "border-[#2C1810]/20 text-[#2C1810] hover:bg-[#FAF8F5]"
          }`}
        >
          <RotateCcw size={13} /> Restart
        </button>

        <button
          type="button"
          onClick={onNext}
          disabled={isEmpty || isConcluded}
          className={`flex items-center gap-2 px-6 py-2.5 rounded-full text-[12px] font-bold uppercase tracking-widest border transition-all shadow-sm ${
            isEmpty || isConcluded
              ? "bg-gray-100 text-gray-400 border-transparent cursor-not-allowed"
              : "bg-[#2C1810] text-[#C5A059] border-[#C5A059] hover:bg-[#3D2318] hover:scale-105 cursor-pointer"
          }`}
        >
          {isConcluded ? <Gavel size={14} /> : <ChevronRight size={14} />}
          {isConcluded ? "Verdict Delivered" : "Next"}
        </button>
      </div>
    </div>
  );
}