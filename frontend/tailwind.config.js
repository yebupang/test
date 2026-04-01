/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        up: "#ef4444",      // 涨（红色，A股习惯）
        down: "#22c55e",    // 跌（绿色，A股习惯）
      },
    },
  },
  plugins: [],
};
