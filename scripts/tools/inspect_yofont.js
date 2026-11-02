const fs = require('fs');
const path = require('path');

const engineModules = path.join(__dirname, '..', '.agents', 'skills', 'draw-your-font', 'engine', 'node_modules');
const wawoff2 = require(path.join(engineModules, 'wawoff2'));
const opentype = require(path.join(engineModules, 'opentype.js'));

async function inspect() {
  const woff2Buf = fs.readFileSync(path.join(__dirname, 'reel_frame.woff2'));
  const ttfBuf = Buffer.from(await wawoff2.decompress(woff2Buf));
  console.log('Decompressed TTF size:', ttfBuf.length);

  fs.writeFileSync(path.join(__dirname, 'reel_frame.ttf'), ttfBuf);

  const font = opentype.parse(ttfBuf.buffer.slice(ttfBuf.byteOffset, ttfBuf.byteOffset + ttfBuf.byteLength));
  console.log('Font familyName:', font.names.fontFamily);
  console.log('Font fullName:', font.names.fullName);
  console.log('UnitsPerEm:', font.unitsPerEm);
  console.log('Ascender:', font.ascender);
  console.log('Descender:', font.descender);
  console.log('Glyph count:', font.glyphs.length);

  const glyphNames = [];
  for (let i = 0; i < Math.min(font.glyphs.length, 30); i++) {
    glyphNames.push(font.glyphs.get(i).name);
  }
  console.log('First 30 glyphs:', glyphNames.join(', '));
}

inspect().catch(console.error);
