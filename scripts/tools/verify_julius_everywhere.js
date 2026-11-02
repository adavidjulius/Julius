const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

console.log('=== VERIFYING JULIUS (TEXT) & JETBRAINS MONO (CODE) INTEGRATION ===\n');

const checks = [];

function check(name, fn) {
  try {
    const result = fn();
    if (result) {
      console.log(`✅ PASS: ${name}`);
      checks.push({ name, pass: true });
    } else {
      console.log(`❌ FAIL: ${name}`);
      checks.push({ name, pass: false, error: 'Condition returned false' });
    }
  } catch (err) {
    console.log(`❌ FAIL: ${name} -> ${err.message}`);
    checks.push({ name, pass: false, error: err.message });
  }
}

// 1. Check Julius font files & glyph count
check('Julius font family contains 115 glyphs with fixed symbols (#, _, @, &, *, <, >)', () => {
  const exts = ['.ttf', '.otf', '.woff', '.woff2'];
  const base = path.join(__dirname, '..', 'Julius_Fonts');
  return exts.every(ext => 
    fs.existsSync(path.join(base, `Julius-Regular${ext}`)) &&
    fs.existsSync(path.join(base, `Julius-Bold${ext}`))
  );
});

// 2. Check macOS System Fonts for both Julius and JetBrains Mono
check('Julius and JetBrains Mono installed in ~/Library/Fonts/', () => {
  const home = process.env.HOME || require('os').homedir();
  const fontDir = path.join(home, 'Library', 'Fonts');
  return fs.existsSync(path.join(fontDir, 'Julius-Regular.ttf')) &&
         fs.existsSync(path.join(fontDir, 'JetBrainsMono-Regular.ttf'));
});

// 3. Check macOS font registration
check('macOS fontconfig detects Julius and JetBrains Mono', () => {
  const out1 = execSync('fc-list : family | grep -i Julius || true', { encoding: 'utf8' });
  const out2 = execSync('fc-list : family | grep -i "JetBrains Mono" || true', { encoding: 'utf8' });
  return out1.toLowerCase().includes('julius') && out2.toLowerCase().includes('jetbrains mono');
});

// 4. Check .vscode/settings.json (JetBrains Mono for coding)
check('.vscode/settings.json configures editor & terminal with JetBrains Mono at normal size', () => {
  const settingsPath = path.join(__dirname, '..', '.vscode', 'settings.json');
  const json = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
  return json['editor.fontFamily'].includes('JetBrains Mono') &&
         json['terminal.integrated.fontFamily'].includes('JetBrains Mono') &&
         json['editor.fontSize'] === 13 &&
         json['terminal.integrated.fontSize'] === 12 &&
         json['editor.fontLigatures'] === true;
});

// 5. Check docs/index.html (Julius for text, JetBrains Mono for code)
check('docs/index.html uses Julius for text and JetBrains Mono for code', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'docs', 'index.html'), 'utf8');
  return html.includes("font-family: 'Julius'") &&
         html.includes("font-family: 'JetBrains Mono'") &&
         html.includes("--font-apple: 'Julius'") &&
         html.includes("--font-mono: 'JetBrains Mono'") &&
         fs.existsSync(path.join(__dirname, '..', 'docs', 'fonts', 'JetBrainsMono-Regular.woff2'));
});

// 6. Check frontend/assets/ (Julius for UI, JetBrains Mono for code)
check('frontend/assets/ has Julius for UI and JetBrains Mono for code', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'assets', 'index-CuCOA579.css'), 'utf8');
  const js = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'assets', 'index-DvVhnTG0.js'), 'utf8');
  return css.includes("font-family: 'Julius'") &&
         css.includes("font-family: 'JetBrains Mono'") &&
         css.includes("--font-mono: 'JetBrains Mono'") &&
         js.includes("fontFamily:\"'Julius'") &&
         fs.existsSync(path.join(__dirname, '..', 'frontend', 'assets', 'JetBrainsMono-Regular.woff2'));
});

// 7. Check julius-apps
check('julius-apps use Julius for app UI and JetBrains Mono for code', () => {
  const css1 = fs.readFileSync(path.join(__dirname, '..', 'julius-apps', 'do-list-where', 'src', 'style.css'), 'utf8');
  const css2 = fs.readFileSync(path.join(__dirname, '..', 'julius-apps', 'i-want-ui', 'src', 'style.css'), 'utf8');
  return css1.includes("--font: 'Julius'") &&
         css1.includes("--font-mono: 'JetBrains Mono'") &&
         css2.includes("--font: 'Julius'") &&
         css2.includes("--font-mono: 'JetBrains Mono'");
});

// 8. Check widget_portal.py (Julius for primary, JetBrains Mono for mono)
check('src/components/widget_portal.py uses Julius for primary and JetBrains Mono for mono', () => {
  const code = fs.readFileSync(path.join(__dirname, '..', 'src', 'components', 'widget_portal.py'), 'utf8');
  return code.includes("--font-primary: 'Julius'") &&
         code.includes("--font-mono: 'JetBrains Mono'");
});

// 9. Check app_builder/builder.py
check('src/app_builder/builder.py uses Julius font for web app scaffolding', () => {
  const code = fs.readFileSync(path.join(__dirname, '..', 'src', 'app_builder', 'builder.py'), 'utf8');
  return code.includes("--font: 'Julius'");
});

// 10. Check julius_gui.py
check('julius_gui.py uses Julius for web views', () => {
  const code = fs.readFileSync(path.join(__dirname, '..', 'julius_gui.py'), 'utf8');
  return code.includes("font-family: 'Julius'");
});

// 11. Check install.sh & start_tui.sh
check('install.sh and start_tui.sh deploy both Julius and JetBrains Mono', () => {
  const install = fs.readFileSync(path.join(__dirname, '..', 'install.sh'), 'utf8');
  const tui = fs.readFileSync(path.join(__dirname, '..', 'start_tui.sh'), 'utf8');
  return install.includes("Installing Julius typography & JetBrains Mono coding fonts") &&
         tui.includes("JetBrainsMono-Regular.ttf");
});

// 12. Check Terminal.app profile
check('macOS Terminal.app defaults to JetBrains Mono profile for code & CLI', () => {
  const out = execSync('defaults read com.apple.Terminal "Default Window Settings"', { encoding: 'utf8' }).trim();
  return out === 'JetBrains Mono';
});

console.log('\n----------------------------------------');
const passed = checks.filter(c => c.pass).length;
const total = checks.length;
console.log(`TOTAL: ${passed}/${total} checks passed.`);
if (passed === total) {
  console.log('🌟 ALL SYSTEM-WIDE TYPOGRAPHY CHECKS PASSED PERFECTLY!');
  process.exit(0);
} else {
  console.log('⚠️ Some checks failed.');
  process.exit(1);
}
