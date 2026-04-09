# MootCourt.ai Design System & Styling Rules

Welcome to the central design matrix for MootCourt.ai. Because this application simulates a highly professional, high-stakes legal environment, **strict adherence to these UI rules is required** to prevent the app from feeling like a generic generic chat tool.

## Philosophy
The UI should feel tactile, grounded, and physical. We achieve this by mapping out rich wooden aesthetics, manila-paper textures, and traditional serif typography, contrasted perfectly with glowing digital semantic elements.

## 1. Using Centralized Colors
Avoid arbitrary hex classes in Tailwind (e.g. `bg-[#5D4037]`). Instead, map them to our internal variables provided in `src/index.css`.
*   **Moot Court Brown**: `var(--color-primary-brown)` -> The core color for action buttons and text.
*   **Moot Court Gold**: `var(--color-gold)` -> Used strictly for highlights, active borders, and the .ai suffix logo.
*   **Wood Assets**: Use `wood-dark` and `wood-deep` exclusively for courtroom furniture. Do not use generic tailwind grays.

## 2. Typography Rules (`typography.js`)
*   **Heading (`Lora`)**: Used for the Master Logo (`font-heading font-extrabold text-primaryBrown`), Transcripts, and structured Legal Notepad input (`font-serif`).
*   **Body (`Inter`)**: All application generic UI, button labels, and hover tooltips. Keep buttons uppercase and aggressively tracked (`tracking-widest` or `tracking-[0.2em]`).
*   **Mono (`Roboto Mono`)**: Reserved exclusively for "System" entities like Firmware status, IPC tag labels (`FIR No`, `IPC 379`), and tiny badges.

## 3. Creating Depth & Shadows (`theme.js`)
Instead of generic shadows, use the physical environment principles:
*   Elements closer to the user (e.g., The Player Podium) should cast `shadow-[0_-15px_40px_rgba(0,0,0,0.5)]` dropping **behind** the podium.
*   Judges cast heavy `shadow-[0_20px_50px_rgba(0,0,0,0.8)]` straight down onto the floor plane.
*   Use `[transform:perspective(1000px)_rotateX(20deg)]` on floor matrices to enforce the 3D room.

## 4. How to Import JS Styles
If you need to push styles directly into a dynamic SVG or a Framer Motion animation, import the `theme.js` values directly:
```javascript
import { colors } from '../styles/theme';
<motion.div animate={{ borderColor: colors.primary.gold }} />
```
