module.exports = {content: ["./templates/home.html"],
      darkMode: "class",
      theme: {
        extend: {
          colors: {
            primary: "#2563EB",
            "background-light": "#FAFAFC",
            "background-dark": "#060B17",
            accent: {
              glow: "#3B82F6",
              emerald: "#10B981",
              slate: "#64748B"
            }
          },
          fontFamily: {
            display: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Arial', 'sans-serif'],
            mono: ['Consolas', 'monospace'],
          },
          borderRadius: {
            DEFAULT: "1rem",
            '2xl': "1.25rem",
            '3xl': "1.75rem",
            '4xl': "2.25rem",
          },
          boxShadow: {
            'glow': '0 0 50px -10px rgba(37, 99, 235, 0.35)',
            'card-dark': '0 20px 40px -15px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.08)',
            'card-light': '0 20px 40px -15px rgba(15, 23, 42, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.9)',
          }
        },
      },
    };
