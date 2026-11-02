const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');
const potrace = require('../.agents/skills/draw-your-font/engine/node_modules/potrace');
const fs = require('fs');
const path = require('path');

async function testTrace() {
  const img1 = process.env.IMG_PATH || '/tmp/glyph.png';

  // Crop letter 'A' (Col 0, Row 0 in UPPERCASE): X: 135..170, Y: 350..385
  // First extract the crop
  const crop = await sharp(img1)
    .extract({ left: 135, top: 350, width: 35, height: 35 })
    .toBuffer();

  fs.writeFileSync(path.join(__dirname, 'crop_A.png'), crop);

  // Now create a high-res thresholded version:
  // Upscale by 8x (280x280) with lanczos/cubic, threshold to clean black/white
  const upscaled = await sharp(img1)
    .extract({ left: 135, top: 350, width: 35, height: 35 })
    .resize(280, 280, { kernel: 'lanczos3' })
    .threshold(160)
    .toBuffer();

  fs.writeFileSync(path.join(__dirname, 'upscaled_A.png'), upscaled);

  // Trace with potrace
  potrace.trace(upscaled, {
    turdSize: 10,
    optTolerance: 0.2,
    threshold: 128
  }, (err, svg) => {
    if (err) throw err;
    fs.writeFileSync(path.join(__dirname, 'traced_A.svg'), svg);
    console.log('Traced A SVG length:', svg.length);
    console.log('SVG content:\n', svg);
  });
}

testTrace();
