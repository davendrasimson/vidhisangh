/** VidhiSangh Tailwind configuration.
 *  Colors reference CSS custom properties (design tokens in styles.scss) so a
 *  single source of truth drives both Tailwind utilities and Angular Material,
 *  and dark mode is a class toggle on <html>. */
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: 'rgb(var(--vs-brand) / <alpha-value>)',
          fg: 'rgb(var(--vs-brand-fg) / <alpha-value>)',
        },
        surface: {
          DEFAULT: 'rgb(var(--vs-surface) / <alpha-value>)',
          raised: 'rgb(var(--vs-surface-raised) / <alpha-value>)',
          sunken: 'rgb(var(--vs-surface-sunken) / <alpha-value>)',
        },
        content: {
          DEFAULT: 'rgb(var(--vs-text) / <alpha-value>)',
          muted: 'rgb(var(--vs-text-muted) / <alpha-value>)',
        },
        line: 'rgb(var(--vs-border) / <alpha-value>)',
        success: 'rgb(var(--vs-success) / <alpha-value>)',
        warning: 'rgb(var(--vs-warning) / <alpha-value>)',
        danger: 'rgb(var(--vs-danger) / <alpha-value>)',
      },
      borderRadius: {
        card: '14px',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px rgb(15 23 42 / 0.05), 0 6px 20px rgb(15 23 42 / 0.08)',
        'card-hover': '0 4px 8px rgb(15 23 42 / 0.06), 0 12px 32px rgb(15 23 42 / 0.12)',
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
};
