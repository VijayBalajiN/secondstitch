// Garment drawings for the "where does it need fixing?" picker. Each has pins (spots); a spot lists the
// service ids (from /api/catalogue) that fix that part of the garment. Drawn flat on pattern paper:
// ink outline, dashed topstitching, tape-yellow trims.

const INK = "#1f2a44";
const PAPER = "#efe4c8";
const STITCH = "#c8442f";

const body = (d, extra = "") =>
  `<path d="${d}" fill="${PAPER}" stroke="${INK}" stroke-width="2.6" stroke-linejoin="round"/>${extra}`;
const stitch = (d) => `<path d="${d}" fill="none" stroke="${STITCH}" stroke-width="1.8" stroke-dasharray="5 4" stroke-linecap="round"/>`;
const line = (d) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`;
const btn = (x, y) => `<circle cx="${x}" cy="${y}" r="4.6" fill="#fbf7ec" stroke="${INK}" stroke-width="1.6"/><path d="M${x - 1.6} ${y}h3.2M${x} ${y - 1.6}v3.2" stroke="${INK}" stroke-width="1"/>`;

const GARMENTS = [
  {
    id: "trousers", label: "g.trousers",
    art: body("M80 30 L220 30 L228 170 L214 350 L156 350 L150 195 L144 350 L86 350 L72 170 Z") +
      body("M80 30 H220 L221 54 H79 Z") +
      line("M92 24v36M122 24v36M178 24v36M208 24v36") +
      stitch("M150 54 V112 Q150 130 137 127") + stitch("M82 58 Q104 112 138 106") + stitch("M218 58 Q196 112 162 106") +
      stitch("M89 334 H146") + stitch("M154 334 H211") + btn(150, 44),
    spots: [
      { id: "waist", x: 196, y: 44, name: "spot.waist", services: ["waist", "button", "elastic"] },
      { id: "fly", x: 150, y: 96, name: "spot.fly", services: ["fly-zip"] },
      { id: "legs", x: 105, y: 215, name: "spot.legs", services: ["taper", "open-seam", "darn"] },
      { id: "hem", x: 185, y: 338, name: "spot.hem", services: ["trouser-hem", "jeans-original-hem", "salwar-shorten"] },
    ],
  },
  {
    id: "kurta", label: "g.kurta",
    art: body("M105 38 L135 38 Q150 66 165 38 L195 38 L254 92 L238 134 L206 110 L214 340 L86 340 L94 110 L62 134 L46 92 Z") +
      line("M150 64 V122") + btn(150, 80) + btn(150, 100) + btn(150, 120) +
      stitch("M90 322 H210") + stitch("M58 124 L84 104") + stitch("M242 124 L216 104") + line("M214 340 V300M86 340 V300"),
    spots: [
      { id: "neck", x: 128, y: 62, name: "spot.neck", services: ["button"] },
      { id: "sleeve", x: 240, y: 108, name: "spot.sleeve", services: ["sleeve-shorten", "sleeve-cuff"] },
      { id: "fit", x: 160, y: 200, name: "spot.fit", services: ["kurta-resize", "side-seams"] },
      { id: "zip", x: 100, y: 230, name: "spot.zip", services: ["dress-zip"] },
      { id: "hem", x: 150, y: 328, name: "spot.hem", services: ["kurta-hem", "lace"] },
    ],
  },
  {
    id: "shirt", label: "g.shirt",
    art: body("M118 34 L150 56 L182 34 L210 42 L264 214 L240 224 L208 112 L214 340 L86 340 L92 112 L60 224 L36 214 L90 42 Z") +
      body("M118 34 L150 56 L182 34 L172 26 L150 42 L128 26 Z") +
      line("M150 56 V340") + [90, 130, 170, 210, 250, 290].map((y) => btn(150, y)).join("") +
      stitch("M44 200 L68 212") + stitch("M256 200 L232 212") + stitch("M92 330 H146") + stitch("M154 330 H208"),
    spots: [
      { id: "shoulder", x: 203, y: 56, name: "spot.shoulder", services: ["shoulder"] },
      { id: "sleeve", x: 246, y: 150, name: "spot.sleeve", services: ["sleeve-shorten", "sleeve-cuff"] },
      { id: "buttons", x: 176, y: 130, name: "spot.buttons", services: ["button"] },
      { id: "fit", x: 106, y: 220, name: "spot.fit", services: ["side-seams", "blouse"] },
      { id: "repair", x: 184, y: 300, name: "spot.repair", services: ["open-seam", "darn"] },
    ],
  },
  {
    id: "blazer", label: "g.blazer",
    art: body("M108 30 L150 62 L192 30 L240 54 L272 224 L246 232 L216 112 L224 336 L76 336 L84 112 L54 232 L28 224 L60 54 Z") +
      line("M108 30 L130 104 L150 62 M192 30 L170 104 L150 62 M150 62 V336") + btn(150, 190) + btn(150, 230) +
      line("M92 250 H132 M168 250 H208") + stitch("M56 214 L80 224") + stitch("M244 214 L220 224") + stitch("M82 326 H218"),
    spots: [
      { id: "shoulder", x: 226, y: 62, name: "spot.shoulder", services: ["shoulder"] },
      { id: "sleeve", x: 258, y: 170, name: "spot.sleeve", services: ["blazer-sleeve"] },
      { id: "zip", x: 150, y: 150, name: "spot.zip", services: ["jacket-zip"] },
      { id: "lining", x: 108, y: 285, name: "spot.lining", services: ["lining"] },
      { id: "fit", x: 196, y: 200, name: "spot.fit", services: ["side-seams", "refit"] },
    ],
  },
  {
    id: "lehenga", label: "g.lehenga",
    art: body("M100 62 H200 L268 322 Q150 352 32 322 Z") +
      `<path d="M42 298 Q150 326 258 298 L268 322 Q150 352 32 322 Z" fill="#f3e3a3" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>` +
      stitch("M48 312 Q150 340 252 312") +
      body("M104 36 H196 L200 62 H100 Z") + btn(150, 49) + stitch("M110 86 Q150 96 190 86") + stitch("M96 130 Q150 142 204 130"),
    spots: [
      { id: "waist", x: 190, y: 46, name: "spot.waist", services: ["lehenga-waist", "elastic"] },
      { id: "zip", x: 186, y: 100, name: "spot.zip", services: ["dress-zip"] },
      { id: "flare", x: 100, y: 205, name: "spot.flare", services: ["flare"] },
      { id: "border", x: 150, y: 330, name: "spot.border", services: ["saree-fall", "lace", "kurta-hem"] },
    ],
  },
];
