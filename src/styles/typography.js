export const typography = {
  fonts: {
    heading: "'Lora', serif",               // For application logo, firm names, and phase titles
    body: "'Inter', sans-serif",            // General scalable UI, tooltips, buttons
    mono: "'Roboto Mono', monospace",       // System feedback, small case numbers, badges
    document: "'Lora', serif",              // Transcripts and pleadings body content
  },
  weights: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    extrabold: 800,
    black: 900,
  },
  letterSpacing: {
    tight: "-0.02em",
    normal: "0",
    wide: "0.05em",
    widest: "0.2em",    // Heavily used for formal uppercase tags!
    badge: "0.4em",     // Very wide formatting for tiny tracking labels
  }
};
