const sharp = require('../.agents/skills/draw-your-font/engine/node_modules/sharp');

async function checkIJ() {
  const imgPath = process.env.IMG_PATH || '/tmp/glyph.png';
  const { data, info } = await sharp(imgPath).raw().toBuffer({ resolveWithObject: true });
  const w = info.width;

  console.log('Pixels around i (X: 220..230, Y: 205..230):');
  for (let y = 205; y <= 230; y++) {
    let row = `Y=${y}: `;
    for (let x = 220; x <= 230; x++) {
      const idx = (y * w + x) * info.channels;
      row += data[idx] < 120 ? '#' : '.';
    }
    console.log(row);
  }

  console.log('\nPixels around j (X: 295..305, Y: 205..235):');
  for (let y = 205; y <= 235; y++) {
    let row = `Y=${y}: `;
    for (let x = 295; x <= 305; x++) {
      const idx = (y * w + x) * info.channels;
      row += data[idx] < 120 ? '#' : '.';
    }
    console.log(row);
  }
}

checkIJ();
