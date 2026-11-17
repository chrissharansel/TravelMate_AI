const v = (n) => `rgb(var(--${n}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: { paper: v("paper"), card: v("card"), ink: v("ink"), muted: v("muted"), teal: v("teal"),
                saffron: v("saffron"), line: v("line"), bad: v("bad"), good: v("good") },
      fontFamily: { display: ["Fraunces", "Georgia", "serif"], sans: ["Instrument Sans", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
