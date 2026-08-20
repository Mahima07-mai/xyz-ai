/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // --- Design tokens (see README "Design system") ---
        // A school-register palette: chalkboard greens and slate for the
        // shared chat/AI surfaces, warm parchment for the four portal
        // shells, and one ink and one signal pair for text/status.
        chalk: {
          25: "#F8FAF7",
          50: "#EFF4EF",
          100: "#D8E4D9",
          200: "#B2C9B4",
          400: "#5C8264",
          600: "#2E4F36",
          800: "#1F3A2E",
          900: "#152A22",
        },
        parchment: {
          50: "#FBF8F0",
          100: "#F6F1E4",
          200: "#ECE3CC",
        },
        ink: {
          400: "#5B6660",
          600: "#33403A",
          900: "#1B1F3B",
        },
        marigold: {
          400: "#E8B94A",
          500: "#D9A62F",
          600: "#B5842A",
        },
        rust: {
          400: "#C46654",
          500: "#B5473B",
          600: "#933A30",
        },
      },
      fontFamily: {
        display: ["\"Fraunces\"", "\"Noto Serif\"", "serif"],
        body: [
          "\"IBM Plex Sans\"",
          "\"IBM Plex Sans Devanagari\"",
          "\"IBM Plex Sans Tamil\"",
          "system-ui",
          "sans-serif",
        ],
        mono: ["\"IBM Plex Mono\"", "ui-monospace", "monospace"],
      },
      boxShadow: {
        chalk: "0 1px 0 0 rgba(255,255,255,0.06) inset, 0 8px 24px -12px rgba(21,42,34,0.45)",
      },
      backgroundImage: {
        "chalk-fiber": "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.035) 1px, transparent 0)",
      },
      backgroundSize: {
        fiber: "5px 5px",
      },
    },
  },
  plugins: [],
};
