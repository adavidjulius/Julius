// Verification script for font construction using opentype.js
const path = require('path');
const fs = require('fs');

const engineModules = path.join(__dirname, '..', '.agents', 'skills', 'draw-your-font', 'engine', 'node_modules');
const opentype = require(path.join(engineModules, 'opentype.js'));
const ttf2woff = require(path.join(engineModules, 'ttf2woff'));
const wawoff2 = require(path.join(engineModules, 'wawoff2'));

console.log('Modules loaded successfully: opentype, ttf2woff, wawoff2');

const notdefPath = new opentype.Path();
notdefPath.moveTo(50, 0);
notdefPath.lineTo(450, 0);
notdefPath.lineTo(450, 700);
notdefPath.lineTo(50, 700);
notdefPath.close();
notdefPath.moveTo(100, 50);
notdefPath.lineTo(100, 650);
notdefPath.lineTo(400, 650);
notdefPath.lineTo(400, 50);
notdefPath.close();

const notdef = new opentype.Glyph({
  name: '.notdef',
  unicode: 0,
  advanceWidth: 500,
  path: notdefPath
});

const font = new opentype.Font({
  familyName: 'JuliusVerification',
  styleName: 'Regular',
  unitsPerEm: 1000,
  ascender: 800,
  descender: -200,
  glyphs: [notdef]
});

const buf = Buffer.from(font.toArrayBuffer());
console.log('Generated TTF bytes:', buf.length);

async function testWoff() {
  const woffBuf = Buffer.from(ttf2woff(buf));
  console.log('Generated WOFF bytes:', woffBuf.length);
  const woff2Buf = Buffer.from(await wawoff2.compress(buf));
  console.log('Generated WOFF2 bytes:', woff2Buf.length);
}

testWoff().then(() => console.log('Verification passed!'));
