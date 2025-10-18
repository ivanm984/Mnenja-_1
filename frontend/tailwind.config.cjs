module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{vue,ts,js,tsx,jsx}"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f5f7ff',
          100: '#e6edff',
          200: '#c5d5ff',
          500: '#2563eb',
          600: '#1d4ed8'
        },
        success: '#16a34a',
        warning: '#f97316',
        danger: '#dc2626'
      },
      boxShadow: {
        card: '0 20px 45px rgba(15, 23, 42, 0.12)',
        soft: '0 12px 30px rgba(15, 23, 42, 0.08)'
      },
      borderRadius: {
        xl: '22px',
        lg: '18px'
      },
      fontFamily: {
        inter: ['Inter', 'system-ui', 'sans-serif']
      }
    }
  },
  plugins: []
};
