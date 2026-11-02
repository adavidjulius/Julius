# Julius Logo Asset Pack

High-fidelity vector SVG and raster icons generated from the official Julius logo artwork.

## Color Palette
- **Primary Green**: `#7ED321`
  - RGB: `rgb(126, 211, 33)`
  - HSL: `hsl(93, 73%, 48%)`
- **Monochrome White**: `#FFFFFF`
- **Monochrome Black**: `#000000`
- **Badge Dark BG**: `#0F172A`

---

## Directory Structure

```
Julius Logo/
├── logo.svg                     # Master responsive SVG (viewBox 0 0 512 512)
├── Julius Logo.png              # Master high-res 1024x1024 PNG
├── favicon.ico                  # Multi-resolution ICO (16x16, 32x32, 48x48)
├── icon.icns                    # macOS Apple Icon Image
├── svg/
│   ├── logo.svg                 # Fluid scalable vector
│   ├── logo-original.svg        # Original 576x576 canvas
│   ├── favicon.svg              # 32x32 SVG favicon
│   ├── logo-white.svg           # Monochrome white (for dark mode)
│   ├── logo-black.svg           # Monochrome black (for print)
│   ├── logo-badge-dark.svg      # App icon badge on dark slate background
│   ├── logo-badge-light.svg     # App icon badge on white background
│   ├── logo-16x16.svg           # Small favicon
│   ├── logo-24x24.svg           # Toolbar icon
│   ├── logo-32x32.svg           # Standard favicon
│   ├── logo-48x48.svg           # Windows small icon
│   ├── logo-64x64.svg           # Medium icon
│   ├── logo-96x96.svg           # High-DPI icon
│   ├── logo-128x128.svg         # Dock / App icon
│   ├── logo-180x180.svg         # Apple touch icon
│   ├── logo-192x192.svg         # Android PWA home screen
│   ├── logo-256x256.svg         # App store standard
│   ├── logo-384x384.svg         # Android splash icon
│   ├── logo-512x512.svg         # PWA / Web store master
│   └── logo-1024x1024.svg       # Retina display master
└── png/
    ├── logo-16x16.png
    ├── logo-24x24.png
    ├── logo-32x32.png
    ├── logo-48x48.png
    ├── logo-64x64.png
    ├── logo-96x96.png
    ├── logo-128x128.png
    ├── logo-180x180.png
    ├── logo-192x192.png
    ├── logo-256x256.png
    ├── logo-384x384.png
    ├── logo-512x512.png
    ├── logo-1024x1024.png
    ├── logo-badge-dark-512x512.png
    ├── logo-badge-light-512x512.png
    └── favicon.ico
```

The `svg/` directory at the repository root contains identical SVG vector files for direct reference.

---

## Usage Examples

### 1. HTML Web Favicon
```html
<link rel="icon" type="image/svg+xml" href="/svg/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/Julius Logo/png/logo-32x32.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/Julius Logo/png/logo-180x180.png" />
```

### 2. React / JSX Component
```tsx
export function JuliusLogo({ size = 32, color = "#7ED321", className = "" }: { size?: number; color?: string; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <path fill={color} d="M 400.67 96.49 c -6.84 0.53 -15.69 2.00 -20.62 3.38 -2.09 0.62 -4.53 1.24 -5.38 1.47 -1.56 0.31 -4.27 1.29 -6.98 2.49 -0.80 0.36 -2.22 0.93 -3.16 1.24 -3.20 1.16 -13.60 6.80 -18.53 10.04 -12.84 8.58 -26.22 21.47 -37.47 36.13 -5.29 6.93 -13.42 19.16 -17.07 25.64 -0.49 0.84 -2.27 3.96 -3.91 6.89 -2.67 4.71 -9.87 19.11 -12.00 24.00 -0.44 0.98 -1.51 3.38 -2.44 5.33 -2.76 5.96 -10.67 26.22 -13.38 34.31 -1.38 4.22 -2.71 7.56 -2.84 7.47 -0.18 -0.13 -0.44 -3.96 -0.58 -8.53 -0.31 -8.80 -1.33 -22.27 -2.09 -27.47 -0.22 -1.73 -0.62 -4.62 -0.89 -6.44 -0.76 -5.87 -3.20 -18.09 -4.22 -21.33 -0.36 -1.11 -1.29 -4.09 -2.04 -6.67 -1.29 -4.27 -2.36 -7.33 -4.36 -12.22 -1.87 -4.71 -7.87 -16.00 -10.44 -19.78 -8.13 -11.82 -19.33 -22.18 -30.04 -27.73 -1.82 -0.98 -4.00 -2.13 -4.80 -2.58 -0.76 -0.44 -3.29 -1.47 -5.56 -2.31 -12.00 -4.44 -19.38 -5.96 -34.98 -7.16 -7.51 -0.58 -10.44 -0.62 -16.67 -0.22 -12.44 0.80 -24.62 2.40 -34.00 4.44 -1.11 0.22 -4.00 0.84 -6.44 1.38 -7.11 1.51 -13.56 3.24 -28.00 7.56 -5.64 1.69 -6.89 2.18 -6.89 2.71 0.00 0.22 0.36 0.53 0.76 0.67 0.44 0.18 2.09 1.02 3.69 1.96 1.60 0.89 4.31 2.36 6.00 3.29 8.13 4.40 27.91 18.62 36.00 25.96 16.09 14.53 31.38 31.29 42.58 46.62 7.42 10.22 18.71 26.89 19.38 28.71 0.09 0.27 0.93 1.60 1.82 2.93 1.47 2.13 7.11 11.91 7.11 12.22 0.00 0.09 0.93 1.69 2.04 3.60 3.73 6.31 14.58 27.60 18.18 35.73 0.93 2.09 2.18 4.89 2.76 6.22 0.62 1.33 2.09 4.62 3.29 7.33 1.20 2.67 2.40 5.24 2.62 5.64 0.27 0.44 0.44 0.98 0.44 1.24 0.00 0.27 0.36 1.29 0.84 2.36 0.44 1.02 1.29 2.98 1.82 4.31 2.00 4.98 4.09 10.04 4.67 11.33 0.62 1.51 1.33 3.38 4.93 13.11 6.80 18.62 16.00 46.36 19.33 58.44 0.27 0.98 0.67 2.27 0.84 2.89 0.18 0.62 0.58 1.91 0.84 2.89 0.27 0.98 0.98 3.38 1.60 5.33 0.58 1.96 1.38 4.67 1.73 6.00 0.36 1.33 0.98 3.56 1.38 4.89 0.36 1.33 0.89 3.24 1.07 4.22 0.49 2.09 2.76 10.84 3.82 14.67 0.44 1.47 0.93 3.33 1.11 4.13 0.71 3.02 1.29 2.49 2.40 -2.13 0.40 -1.82 1.16 -4.93 1.60 -6.89 0.44 -1.96 1.60 -6.67 2.49 -10.44 1.56 -6.71 3.69 -14.98 5.51 -21.78 4.44 -16.40 6.18 -22.84 7.11 -26.00 0.40 -1.33 0.93 -3.29 1.73 -6.13 0.22 -0.76 0.93 -3.11 1.60 -5.20 0.67 -2.09 2.04 -6.67 3.11 -10.22 2.49 -8.36 11.11 -34.22 13.82 -41.33 3.87 -10.40 4.22 -11.33 4.93 -13.33 0.84 -2.53 2.71 -7.38 3.47 -9.11 0.31 -0.76 2.18 -5.24 4.13 -10.00 4.53 -11.11 6.84 -16.40 10.98 -25.11 1.24 -2.71 2.89 -6.18 3.60 -7.78 4.13 -9.16 16.76 -32.71 21.33 -39.91 0.84 -1.29 1.51 -2.40 1.51 -2.49 0.00 -1.07 15.91 -24.89 21.24 -31.91 16.98 -22.18 30.00 -35.78 48.53 -50.84 4.93 -4.00 16.67 -12.18 20.67 -14.40 6.84 -3.78 12.67 -7.24 12.67 -7.51 0.00 -0.18 -0.84 -0.53 -1.87 -0.80 -1.07 -0.27 -3.42 -0.89 -5.24 -1.38 -12.09 -3.29 -28.49 -4.93 -40.22 -4.04 Z" />
    </svg>
  );
}
```

### 3. CSS Inline Background
```css
.julius-brand-icon {
  width: 48px;
  height: 48px;
  background-image: url('/Julius Logo/svg/logo.svg');
  background-repeat: no-repeat;
  background-size: contain;
}
```
