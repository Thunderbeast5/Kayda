import { Mic, Volume2, VolumeX, Send } from "lucide-react";

export default function CourtroomInputBar({
  status,
  activeSpeaker,
  inputText,
  setInputText,
  submitUserInput,
  isListening,
  toggleListening,
  ttsEnabled,
  setTtsEnabled
}) {
  if (status !== "running") return null;

  return (
    <div className="bg-transparent px-4 py-4 z-30 flex flex-col items-center justify-center w-full">
      {/* Active speaker status */}
      <div className="mb-2 text-center">
        <span className={`text-[10px] font-bold uppercase tracking-widest ${activeSpeaker ? 'text-primaryBrown/50' : 'text-gold drop-shadow-md'} flex items-center justify-center gap-1.5 transition-colors`}>
          <span className={`w-1.5 h-1.5 rounded-full ${activeSpeaker ? 'bg-primaryBrown/30' : 'bg-gold animate-pulse'}`}></span>
          {activeSpeaker ? 'Awaiting opposing counsel...' : 'You have the floor — present your argument'}
        </span>
      </div>

      <form onSubmit={submitUserInput} className="w-full max-w-3xl">
        <div className={`flex items-center gap-3 bg-white border border-[#2C1810]/15 rounded-full py-1.5 pl-4 pr-1.5 shadow-[0_4px_25px_rgba(0,0,0,0.06)] transition-all ${activeSpeaker ? 'opacity-70 bg-gray-50' : 'focus-within:border-gold focus-within:ring-2 focus-within:ring-gold/10'}`}>
          
          {/* Plus Action Button */}
          <button 
            type="button" 
            className="text-[#2C1810]/50 hover:text-[#2C1810] transition-colors p-1 cursor-pointer"
            title="Additional Options"
            onClick={() => alert("Chamber Actions:\n\nUse the left sidebar to consult the legal database or raise formal objections.")}
          >
            <span className="text-xl font-light leading-none">+</span>
          </button>

          {/* Input Area */}
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={activeSpeaker !== null}
            placeholder={
              activeSpeaker 
                ? "Opposing counsel is presenting..." 
                : isListening 
                  ? "Listening... speak clearly into your mic..." 
                  : "Ask anything / state your case..."
            }
            className="w-full bg-transparent border-none outline-none py-2 text-[14px] text-[#2C1810] placeholder-[#2C1810]/40"
          />

          {/* Speech-to-Text Microphone Button */}
          <button
            type="button"
            onClick={toggleListening}
            className={`p-1.5 rounded-full transition-all flex items-center justify-center shrink-0 cursor-pointer ${
              isListening 
                ? 'bg-red-500 text-white animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.5)]' 
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            }`}
            title={isListening ? "Stop listening" : "Speech-to-Text (Dictate)"}
          >
            <Mic size={16} />
          </button>

          {/* Text-to-Speech Voice Readout Toggle */}
          <button
            type="button"
            onClick={() => setTtsEnabled(!ttsEnabled)}
            className={`p-1.5 rounded-full transition-all flex items-center justify-center shrink-0 cursor-pointer ${
              ttsEnabled 
                ? 'text-gold hover:bg-gold/10' 
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            }`}
            title={ttsEnabled ? "Mute Readout" : "Unmute Readout"}
          >
            {ttsEnabled ? <Volume2 size={16} className="text-gold" /> : <VolumeX size={16} />}
          </button>

          {/* Send Button */}
          <button
            type="submit"
            disabled={inputText.length < 20 || activeSpeaker !== null}
            className={`p-2 rounded-full transition-all flex items-center justify-center shrink-0 border ${
              inputText.length >= 20 && !activeSpeaker 
                ? 'bg-[#2C1810] text-[#C5A059] border-[#C5A059] hover:bg-[#3D2318] hover:scale-105 shadow-sm cursor-pointer' 
                : 'bg-gray-100 text-gray-400 border-transparent cursor-not-allowed'
            }`}
            title="Submit to Record"
          >
            <Send size={14} />
          </button>
        </div>
      </form>
    </div>
  );
}
