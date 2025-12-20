
/**
 * 全局常量与样式配置 - Liquid Glass 极致版
 */

export const UI_CONFIG = {
  light: {
    CARD_BG: "bg-white/5", // 降低不透明度
    TEXT_PRIMARY: "text-[#1a1a1a]",
    TEXT_SECONDARY: "text-[#2a2a2a]",
    LABEL: "text-[#1a1a1a]/40",
    SHADOW: "shadow-[0_20px_50px_rgba(0,0,0,0.1)]",
    BORDER: "border-white/30",
    BACKDROP: "backdrop-blur-[60px] saturate-[180%]", // 增强模糊和色彩饱和度
    INNER_GLOW: "inset-shadow-sm",
  },
  dark: {
    CARD_BG: "bg-black/10", // 降低不透明度
    TEXT_PRIMARY: "text-white",
    TEXT_SECONDARY: "text-white/80",
    LABEL: "text-white/30",
    SHADOW: "shadow-[0_20px_50px_rgba(0,0,0,0.3)]",
    BORDER: "border-white/10",
    BACKDROP: "backdrop-blur-[60px] saturate-[180%]", // 增强模糊和色彩饱和度
    INNER_GLOW: "inset-shadow-sm",
  },
  FONT_MONO: "font-['JetBrains_Mono']",
  fonts: {
    sans: "font-sans-mode",
    serif: "font-serif-mode",
  }
};

export const SYSTEM_HOTKEY = "Alt + J";
