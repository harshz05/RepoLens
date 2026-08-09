/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          base: "#0B0D13",
          surface: "#131620",
          elevated: "#1A1E2E",
          border: "rgba(255, 255, 255, 0.08)",
          hover: "rgba(255, 255, 255, 0.04)",
        },
        electric: {
          indigo: "#6366F1",
          violet: "#8B5CF6",
          emerald: "#10B981",
          rose: "#F43F5E",
          amber: "#F59E0B",
          cyan: "#06B6D4",
        },
      },
      fontFamily: {
        mono: ["var(--font-fira-code)", "JetBrains Mono", "monospace"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 20px -5px rgba(99, 102, 241, 0.35)",
        "glow-lg": "0 0 35px -5px rgba(99, 102, 241, 0.5)",
      },
    },
  },
  plugins: [],
};
