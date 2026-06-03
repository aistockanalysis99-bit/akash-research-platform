/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#080b12",
          soft: "#0c111b",
          card: "#111824",
          hover: "#18212f",
        },
        line: "#1e2a3d",
        brand: {
          DEFAULT: "#2dd4bf",
          glow: "#5eead4",
          dim: "#0f766e",
        },
        pos: "#34d399",
        neg: "#f87171",
        warn: "#fbbf24",
        info: "#60a5fa",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)",
        glow: "0 0 0 1px rgba(45,212,191,0.15), 0 4px 20px rgba(45,212,191,0.08)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
