// Garments for the "where does it need fixing?" picker. Each is a real photo (/img/pick-*.jpg, 3:4)
// with numbered spots on it. A spot lists the service ids (from /api/catalogue) that fix that part.
// x and y are on a 300 x 400 grid laid over the photo.

const GARMENTS = [
  {
    id: "trousers", label: "g.trousers", photo: "pick-trousers",
    spots: [
      { id: "waist", x: 205, y: 56, name: "spot.waist", services: ["waist", "button", "elastic"] },
      { id: "fly", x: 148, y: 84, name: "spot.fly", services: ["fly-zip"] },
      { id: "legs", x: 100, y: 215, name: "spot.legs", services: ["taper", "open-seam", "darn"] },
      { id: "hem", x: 192, y: 368, name: "spot.hem", services: ["trouser-hem", "jeans-original-hem", "salwar-shorten"] },
    ],
  },
  {
    id: "kurta", label: "g.kurta", photo: "pick-kurta",
    spots: [
      { id: "neck", x: 134, y: 92, name: "spot.neck", services: ["button"] },
      { id: "sleeve", x: 200, y: 165, name: "spot.sleeve", services: ["sleeve-shorten", "sleeve-cuff"] },
      { id: "fit", x: 138, y: 200, name: "spot.fit", services: ["kurta-resize", "side-seams"] },
      { id: "zip", x: 98, y: 168, name: "spot.zip", services: ["dress-zip"] },
      { id: "hem", x: 142, y: 284, name: "spot.hem", services: ["kurta-hem", "lace"] },
    ],
  },
  {
    id: "shirt", label: "g.shirt", photo: "pick-shirt",
    spots: [
      { id: "shoulder", x: 222, y: 84, name: "spot.shoulder", services: ["shoulder"] },
      { id: "sleeve", x: 256, y: 225, name: "spot.sleeve", services: ["sleeve-shorten", "sleeve-cuff"] },
      { id: "buttons", x: 150, y: 150, name: "spot.buttons", services: ["button"] },
      { id: "fit", x: 66, y: 222, name: "spot.fit", services: ["side-seams", "blouse"] },
      { id: "repair", x: 196, y: 330, name: "spot.repair", services: ["open-seam", "darn"] },
    ],
  },
  {
    id: "blazer", label: "g.blazer", photo: "pick-blazer",
    spots: [
      { id: "shoulder", x: 224, y: 90, name: "spot.shoulder", services: ["shoulder"] },
      { id: "sleeve", x: 244, y: 218, name: "spot.sleeve", services: ["blazer-sleeve"] },
      { id: "zip", x: 150, y: 128, name: "spot.zip", services: ["jacket-zip"] },
      { id: "lining", x: 140, y: 322, name: "spot.lining", services: ["lining"] },
      { id: "fit", x: 92, y: 252, name: "spot.fit", services: ["side-seams", "refit"] },
    ],
  },
  {
    id: "lehenga", label: "g.lehenga", photo: "pick-lehenga",
    spots: [
      { id: "waist", x: 128, y: 152, name: "spot.waist", services: ["lehenga-waist", "elastic"] },
      { id: "zip", x: 146, y: 112, name: "spot.zip", services: ["dress-zip"] },
      { id: "flare", x: 92, y: 272, name: "spot.flare", services: ["flare"] },
      { id: "border", x: 140, y: 358, name: "spot.border", services: ["saree-fall", "lace", "kurta-hem"] },
    ],
  },
];
