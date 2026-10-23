import avatarOne from "../assets/avatar/a1.png";
import avatarTwo from "../assets/avatar/a2.png";

export const AVATAR_OPTIONS = [
  { id: "a1", label: "Classic Counsel", src: avatarOne },
  { id: "a2", label: "Modern Counsel", src: avatarTwo },
];

export const DEFAULT_AVATAR = AVATAR_OPTIONS[0].src;

export function getRandomAvatar() {
  return AVATAR_OPTIONS[Math.floor(Math.random() * AVATAR_OPTIONS.length)];
}

export function isGooglePhoto(url) {
  return typeof url === "string" && /(?:googleusercontent\.com|ggpht\.com)/i.test(url);
}
