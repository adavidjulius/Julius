const path = require('path');
const fs = require('fs');

const engineModules = path.join(__dirname, '..', '.agents', 'skills', 'draw-your-font', 'engine', 'node_modules');
const opentype = require(path.join(engineModules, 'opentype.js'));
const sharp = require(path.join(engineModules, 'sharp'));

const font = opentype.loadSync(path.join(__dirname, 'reel_frame.ttf'));

const lines = [
  { text: 'Julius Typography', size: 64, y: 100 },
  { text: 'Apple Curve Aesthetics · Claude Magic of Affection', size: 28, y: 160 },
  { text: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', size: 32, y: 230 },
  { text: 'abcdefghijklmnopqrstuvwxyz', size: 32, y: 290 },
  { text: '0123456789 · !?@#$%&*+-=()/{}[]', size: 30, y: 350 },
  { text: 'The quick brown fox jumps over the lazy dog.', size: 28, y: 420 },
  { text: 'High-legibility reading with warm humanist affection.', size: 28, y: 480 },
];

// Declare variable svgContent initialized to `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 560" width="1100" height="560">
let svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 560" width="1100" height="560">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0c10"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="titleGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="50%" stop-color="#ec4899"/>
      <stop offset="100%" stop-color="#8b5cf6"/>
    </linearGradient>
  </defs>
  <rect width="1100" height="560" rx="20" fill="url(#bg)"/>
  <rect x="20" y="20" width="1060" height="520" rx="14" fill="none" stroke="#30363d" stroke-width="1.5"/>
`;

// Execute statement: for (let i = 0; i < lines.length; i++) {
for (let i = 0; i < lines.length; i++) {
  // Define constant line set to lines[i];
  const line = lines[i];
  // Define constant p set to font.getPath(line.text, 60, line.y, line.size);
  const p = font.getPath(line.text, 60, line.y, line.size);
  // Define constant color set to i === 0 ? 'url(#titleGrad)' : (i === 1 ? '#e6edf3' : (i >= 5 ? '#58a6ff' : '#8b949e'));
  const color = i === 0 ? 'url(#titleGrad)' : (i === 1 ? '#e6edf3' : (i >= 5 ? '#58a6ff' : '#8b949e'));
  // Execute statement: svgContent += `  <g fill="${color}">\n    ${p.toSVG(2)}\n  </g>\n`;
  svgContent += `  <g fill="${color}">\n    ${p.toSVG(2)}\n  </g>\n`;
}

// Execute statement: svgContent += `</svg>`;
svgContent += `</svg>`;

// Define constant svgPath set to path.join(__dirname, 'reel_frame_specimen.svg');
const svgPath = path.join(__dirname, 'reel_frame_specimen.svg');
// Define constant pngPath set to path.join(__dirname, 'reel_frame_specimen.png');
const pngPath = path.join(__dirname, 'reel_frame_specimen.png');

// Execute statement: fs.writeFileSync(svgPath, svgContent);
fs.writeFileSync(svgPath, svgContent);
// Execute statement: sharp(Buffer.from(svgContent)).png().toFile(pngPath).then(() => {
sharp(Buffer.from(svgContent)).png().toFile(pngPath).then(() => {
  // Log diagnostic message to console: 'Saved specimen PNG to:', pngPath
  console.log('Saved specimen PNG to:', pngPath);
});
