#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const { parseArgs } = require('node:util');

// Define constant USAGE set to `draw-your-font - turn a photo of your handwriting into a real font
const USAGE = `draw-your-font - turn a photo of your handwriting into a real font

Usage:
  draw-your-font template [-o template.pdf] [--charset minimal|spanish]
  draw-your-font segment <photo...> [-d workdir] [--delta N] [--cap N]
  draw-your-font build   [-d workdir] (--labels labels.json | --chars "ABC…" | --charset name)
                         [--name "My Handwriting"] [-o font.ttf] [--smooth 0..2]
                         [--weight=-2..2] [--formats ttf,woff,woff2,css]
                         (negative weight needs the = form: --weight=-1)
  draw-your-font make    <photo...> (--chars "ABC…" | --charset name) [build options]
  draw-your-font preview [-d workdir] [--text "…"] [-o preview.png]

Typical flows:
  1. Freeform photo, you know the order you wrote in:
       draw-your-font make photo.jpg --chars "ABCabc" --name "My Hand"
  2. Printed template (order is the charset):
       draw-your-font template -o template.pdf --charset minimal
       # print, write, photograph, then:
       draw-your-font make page1.jpg page2.jpg --charset minimal
  3. Agent-assisted (Claude labels the blobs):
       draw-your-font segment photo.jpg -d work
       # inspect work/contact-1.png, write work/labels.json {"0":"A", …}
       draw-your-font build -d work --labels work/labels.json
`;

// Define constant OPTS set to {
const OPTS = {
  // Define property dir with type { type: 'string', short: 'd', default: 'work' },
  dir: { type: 'string', short: 'd', default: 'work' },
  // Define property out with type { type: 'string', short: 'o' },
  out: { type: 'string', short: 'o' },
  // Define property name with type { type: 'string', default: 'My Handwriting' },
  name: { type: 'string', default: 'My Handwriting' },
  // Define property labels with type { type: 'string' },
  labels: { type: 'string' },
  // Define property chars with type { type: 'string' },
  chars: { type: 'string' },
  // Define property charset with type { type: 'string' },
  charset: { type: 'string' },
  // Define property smooth with type { type: 'string', default: '1' },
  smooth: { type: 'string', default: '1' },
  // Define property weight with type { type: 'string', default: '0' },
  weight: { type: 'string', default: '0' },
  // Define property formats with type { type: 'string', default: 'ttf' },
  formats: { type: 'string', default: 'ttf' },
  // Define property text with type { type: 'string' },
  text: { type: 'string' },
  // Define property delta with type { type: 'string' },
  delta: { type: 'string' },
  // Define property cap with type { type: 'string' },
  cap: { type: 'string' },
  // Define property help with type { type: 'boolean', short: 'h' },
  help: { type: 'boolean', short: 'h' },
};

// Define asynchronous function main()
async function main() {
  // Execute statement: const [cmd, ...rest] = process.argv.slice(2);
  const [cmd, ...rest] = process.argv.slice(2);
  // Check condition: !cmd || cmd === '--help' || cmd === '-h' || cmd === 'help'
  if (!cmd || cmd === '--help' || cmd === '-h' || cmd === 'help') {
    // Log diagnostic message to console: USAGE
    console.log(USAGE);
    // Execute statement: process.exit(cmd ? 0 : 1);
    process.exit(cmd ? 0 : 1);
  }
  // Execute statement: const { values: opt, positionals } = parseArgs({ args: rest, options: OPTS, allowPositionals: true });
  const { values: opt, positionals } = parseArgs({ args: rest, options: OPTS, allowPositionals: true });
  // Check condition: opt.help
  if (opt.help) {
    // Log diagnostic message to console: USAGE
    console.log(USAGE);
    // Execute statement: process.exit(0);
    process.exit(0);
  }
  // Define constant dir set to opt.dir;
  const dir = opt.dir;

  // Check condition: cmd === 'template'
  if (cmd === 'template') {
    // Execute statement: const { generateTemplate } = require('./template');
    const { generateTemplate } = require('./template');
    // Define constant out set to opt.out || 'template.pdf';
    const out = opt.out || 'template.pdf';
    // Asynchronously await promise resolution: generateTemplate(out, { charset: opt.charset || 'minimal' });
    await generateTemplate(out, { charset: opt.charset || 'minimal' });
    // Log diagnostic message to console: `Template written to ${out}. Print it, write with a dark pen, photograph each page.`
    console.log(`Template written to ${out}. Print it, write with a dark pen, photograph each page.`);
    // Return early from function
    return;
  }

  // Check condition: cmd === 'segment' || cmd === 'make'
  if (cmd === 'segment' || cmd === 'make') {
    // Check condition: !positionals.length) fail('No photos given.'
    if (!positionals.length) fail('No photos given.');
    // Execute statement: const { segment } = require('./segment');
    const { segment } = require('./segment');
    // Define constant manifest set to await segment(positionals, dir, {
    const manifest = await segment(positionals, dir, {
      // Define property delta with type opt.delta ? Number(opt.delta) : undefined,
      delta: opt.delta ? Number(opt.delta) : undefined,
      // Define property cap with type opt.cap ? Number(opt.cap) : undefined,
      cap: opt.cap ? Number(opt.cap) : undefined,
    });
    // Log diagnostic message to console: `Found ${manifest.blobs.length} glyph candidates across ${positionals.length} photo(s).`
    console.log(`Found ${manifest.blobs.length} glyph candidates across ${positionals.length} photo(s).`);
    // Log diagnostic message to console: `Crops: ${dir}/crops/  Contact sheet(s): ${dir}/contact-*.png  Data: ${dir}/blobs.json`
    console.log(`Crops: ${dir}/crops/  Contact sheet(s): ${dir}/contact-*.png  Data: ${dir}/blobs.json`);
    // Check condition: cmd === 'segment'
    if (cmd === 'segment') return;
  }

  // Check condition: cmd === 'build' || cmd === 'make'
  if (cmd === 'build' || cmd === 'make') {
    // Asynchronously await promise resolution: build(dir, opt);
    await build(dir, opt);
    // Return early from function
    return;
  }

  // Check condition: cmd === 'preview'
  if (cmd === 'preview') {
    // Execute statement: const { renderPreview } = require('./preview');
    const { renderPreview } = require('./preview');
    // Define constant manifest set to readJSON(path.join(dir, 'manifest.json'), 'Run build first.');
    const manifest = readJSON(path.join(dir, 'manifest.json'), 'Run build first.');
    // Define constant out set to opt.out || path.join(dir, 'preview.png');
    const out = opt.out || path.join(dir, 'preview.png');
    // Asynchronously await promise resolution: renderPreview(manifest, out, { text: opt.text });
    await renderPreview(manifest, out, { text: opt.text });
    // Log diagnostic message to console: `Preview: ${out}`
    console.log(`Preview: ${out}`);
    // Return early from function
    return;
  }

  // Execute statement: fail(`Unknown command "${cmd}".\n\n${USAGE}`);
  fail(`Unknown command "${cmd}".\n\n${USAGE}`);
}

// Define asynchronous function build(dir, opt)
async function build(dir, opt) {
  // Execute statement: const { trace, adjustWeight } = require('./trace');
  const { trace, adjustWeight } = require('./trace');
  // Execute statement: const { placeGlyph } = require('./metrics');
  const { placeGlyph } = require('./metrics');
  // Execute statement: const { buildTTF, toWoff, toWoff2, fontFaceCSS } = require('./assemble');
  const { buildTTF, toWoff, toWoff2, fontFaceCSS } = require('./assemble');
  // Execute statement: const { renderPreview, renderGlyphSheet } = require('./preview');
  const { renderPreview, renderGlyphSheet } = require('./preview');
  // Execute statement: const { CHARSETS } = require('./charsets');
  const { CHARSETS } = require('./charsets');

  // Define constant blobs set to readJSON(path.join(dir, 'blobs.json'), 'Run segment (or make) first.');
  const blobs = readJSON(path.join(dir, 'blobs.json'), 'Run segment (or make) first.');
  // Define constant labels set to resolveLabels(blobs, opt, CHARSETS);
  const labels = resolveLabels(blobs, opt, CHARSETS);

  // Define constant smooth set to Number(opt.smooth);
  const smooth = Number(opt.smooth);
  // Define constant weight set to Math.max(-2, Math.min(2, Number(opt.weight)));
  const weight = Math.max(-2, Math.min(2, Number(opt.weight)));
  // Define constant glyphs set to [];
  const glyphs = [];
  // Define constant seen set to new Set();
  const seen = new Set();
  // Execute statement: for (const blob of blobs.blobs) {
  for (const blob of blobs.blobs) {
    // Declare variable char initialized to labels[blob.id];
    let char = labels[blob.id];
    // Check condition: !char
    if (!char) continue;
    // Set char to char.normalize('NFC');
    char = char.normalize('NFC');
    // Check condition: [...char].length > 1
    if ([...char].length > 1) {
      // Log warning message to console: `  ! "${char}" (blob ${blob.id}) is a multi-character sequence - not supported yet, skipped`
      console.warn(`  ! "${char}" (blob ${blob.id}) is a multi-character sequence - not supported yet, skipped`);
      // Skip to next loop iteration
      continue;
    }
    // Check condition: seen.has(char)
    if (seen.has(char)) {
      // Log warning message to console: `  ! duplicate "${char}" (blob ${blob.id}) - keeping the first one`
      console.warn(`  ! duplicate "${char}" (blob ${blob.id}) - keeping the first one`);
      // Skip to next loop iteration
      continue;
    }
    // Execute statement: seen.add(char);
    seen.add(char);
    // Declare variable png initialized to fs.readFileSync(path.join(dir, blob.crop));
    let png = fs.readFileSync(path.join(dir, blob.crop));
    // Set png to await adjustWeight(png, weight);
    png = await adjustWeight(png, weight);
    // Define constant d set to await trace(png, { smooth });
    const d = await trace(png, { smooth });
    // Check condition: !d
    if (!d) {
      // Log warning message to console: `  ! blob ${blob.id} ("${char}") traced to nothing - skipped`
      console.warn(`  ! blob ${blob.id} ("${char}") traced to nothing - skipped`);
      // Skip to next loop iteration
      continue;
    }
    // Define constant placed set to placeGlyph(d, blob.cropSize, blobs.pad, char);
    const placed = placeGlyph(d, blob.cropSize, blobs.pad, char);
    // Execute statement: glyphs.push({ char, ...placed, source: blob.crop });
    glyphs.push({ char, ...placed, source: blob.crop });
  }
  // Check condition: !glyphs.length) fail('No glyphs to build. Check your labels.'
  if (!glyphs.length) fail('No glyphs to build. Check your labels.');

  // Define constant name set to opt.name;
  const name = opt.name;
  // Define constant base set to (opt.out ? opt.out.replace(/\.\w+$/, '') : path.join(dir, name.replace(/\s+/g, '')));
  const base = (opt.out ? opt.out.replace(/\.\w+$/, '') : path.join(dir, name.replace(/\s+/g, '')));
  // Execute statement: fs.mkdirSync(path.dirname(path.resolve(base)), { recursive: true });
  fs.mkdirSync(path.dirname(path.resolve(base)), { recursive: true });
  // Define constant ttf set to buildTTF(name, glyphs);
  const ttf = buildTTF(name, glyphs);
  // Define constant formats set to opt.formats.split(',').map((s) => s.trim().toLowerCase());
  const formats = opt.formats.split(',').map((s) => s.trim().toLowerCase());
  // Define constant written set to [];
  const written = [];
  // Check condition: formats.includes('ttf') || opt.out
  if (formats.includes('ttf') || opt.out) {
    // Execute statement: fs.writeFileSync(`${base}.ttf`, ttf);
    fs.writeFileSync(`${base}.ttf`, ttf);
    // Execute statement: written.push(`${base}.ttf`);
    written.push(`${base}.ttf`);
  }
  // Check condition: formats.includes('woff')
  if (formats.includes('woff')) {
    // Execute statement: fs.writeFileSync(`${base}.woff`, toWoff(ttf));
    fs.writeFileSync(`${base}.woff`, toWoff(ttf));
    // Execute statement: written.push(`${base}.woff`);
    written.push(`${base}.woff`);
  }
  // Check condition: formats.includes('woff2')
  if (formats.includes('woff2')) {
    // Execute statement: fs.writeFileSync(`${base}.woff2`, await toWoff2(ttf));
    fs.writeFileSync(`${base}.woff2`, await toWoff2(ttf));
    // Execute statement: written.push(`${base}.woff2`);
    written.push(`${base}.woff2`);
  }
  // Check condition: formats.includes('css')
  if (formats.includes('css')) {
    // Execute statement: fs.writeFileSync(`${base}.css`, fontFaceCSS(name, path.basename(base)));
    fs.writeFileSync(`${base}.css`, fontFaceCSS(name, path.basename(base)));
    // Execute statement: written.push(`${base}.css`);
    written.push(`${base}.css`);
  }

  // Define constant manifest set to {
  const manifest = {
    // Import or destructure parameter name
    name,
    // Define property unitsPerEm with type 1000,
    unitsPerEm: 1000,
    // Import or destructure parameter smooth
    smooth,
    // Import or destructure parameter weight
    weight,
    // Define property glyphs with type Object.fromEntries(glyphs.map((g) => [g.char, { d: g.d, advance: g.advance, source: g.source }])),
    glyphs: Object.fromEntries(glyphs.map((g) => [g.char, { d: g.d, advance: g.advance, source: g.source }])),
  };
  // Execute statement: fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(manifest));
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(manifest));
  // Asynchronously await promise resolution: renderPreview(manifest, path.join(dir, 'preview.png'));
  await renderPreview(manifest, path.join(dir, 'preview.png'));
  // Asynchronously await promise resolution: renderGlyphSheet(manifest, path.join(dir, 'glyphs.png'));
  await renderGlyphSheet(manifest, path.join(dir, 'glyphs.png'));

  // Log diagnostic message to console: `Built ${glyphs.length} glyphs → ${written.join(', ')}`
  console.log(`Built ${glyphs.length} glyphs → ${written.join(', ')}`);
  // Log diagnostic message to console: `Preview: ${path.join(dir, 'preview.png')}  Glyph sheet: ${path.join(dir, 'glyphs.png')}`
  console.log(`Preview: ${path.join(dir, 'preview.png')}  Glyph sheet: ${path.join(dir, 'glyphs.png')}`);
  // Define constant missing set to [...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'].filter((c) => !seen.has(c));
  const missing = [...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'].filter((c) => !seen.has(c));
  // Check condition: missing.length) console.log(`Letters not in this font yet: ${missing.join(' ')}`
  if (missing.length) console.log(`Letters not in this font yet: ${missing.join(' ')}`);
}

// Define function resolveLabels(blobs, opt, CHARSETS)
function resolveLabels(blobs, opt, CHARSETS) {
  // Check condition: opt.labels
  if (opt.labels) {
    // Define constant map set to readJSON(opt.labels, '');
    const map = readJSON(opt.labels, '');
    // Return value Object.fromEntries(Object.entries(map).filter(([, v]) => v)); to caller
    return Object.fromEntries(Object.entries(map).filter(([, v]) => v));
  }
  // Execute statement: let chars;
  let chars;
  // Check condition: opt.chars) chars = [...opt.chars.normalize('NFC').replace(/\s+/g, ''
  if (opt.chars) chars = [...opt.chars.normalize('NFC').replace(/\s+/g, '')];
  // Alternative condition check: opt.charset
  else if (opt.charset) {
    // Set chars to CHARSETS[opt.charset];
    chars = CHARSETS[opt.charset];
    // Check condition: !chars) fail(`Unknown charset "${opt.charset}". Available: ${Object.keys(CHARSETS).join(', ')}`
    if (!chars) fail(`Unknown charset "${opt.charset}". Available: ${Object.keys(CHARSETS).join(', ')}`);
  // Execute statement: } else {
  } else {
    // Execute statement: fail('Provide --labels labels.json, --chars "…", or --charset <name>.');
    fail('Provide --labels labels.json, --chars "…", or --charset <name>.');
  }
  // Define constant ids set to blobs.blobs.map((b) => b.id);
  const ids = blobs.blobs.map((b) => b.id);
  // Check condition: chars.length !== ids.length
  if (chars.length !== ids.length) {
    // Execute statement: console.warn(
    console.warn(
      // Execute statement: `  ! ${ids.length} blobs found but ${chars.length} characters given - mapping in order, extras ignored.\n` +
      `  ! ${ids.length} blobs found but ${chars.length} characters given - mapping in order, extras ignored.\n` +
      // Execute statement: `    If this is unexpected, inspect the contact sheet and use --labels for exact control.`
      `    If this is unexpected, inspect the contact sheet and use --labels for exact control.`
    );
  }
  // Return value Object.fromEntries(ids.slice(0, chars.length).map((id, i) => [id, chars[i]])); to caller
  return Object.fromEntries(ids.slice(0, chars.length).map((id, i) => [id, chars[i]]));
}

// Define function readJSON(file, hint)
function readJSON(file, hint) {
  // Check condition: !fs.existsSync(file)) fail(`${file} not found. ${hint}`
  if (!fs.existsSync(file)) fail(`${file} not found. ${hint}`);
  // Return value JSON.parse(fs.readFileSync(file, 'utf8')); to caller
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

// Define function fail(msg)
function fail(msg) {
  // Log error message to console: msg
  console.error(msg);
  // Execute statement: process.exit(1);
  process.exit(1);
}

// Execute statement: main().catch((err) => fail(err.stack || String(err)));
main().catch((err) => fail(err.stack || String(err)));
