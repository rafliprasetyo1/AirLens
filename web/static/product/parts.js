// AirLens Node: data model 3D untuk halaman produk (konsep utama + Beta).
//
// Model: product/models/airlens_node_concept.glb dan airlens_beta.glb (mm, Y ke atas, depan casing = +Z).
// Keduanya dibuat oleh hardware/enclosure-concept/assemble.py dan hardware/enclosure-beta/beta_assemble.py;
// node mesh datar di root dengan posisi rakitan final. Halaman mengelompokkan node per awalan nama.
// placements.json (label, arah tarik keluar, posisi modul) dimuat saat runtime.
//
// Titik label dan ujung kabel di bawah dihitung dari koordinat lokal di build_concept_components.py lewat transformasi
// modul di assemble.py (Pi 5 dan AI HAT+ diputar 180° di sumbu Y). Saat model diganti, hitung ulang dengan cara sama.

export const CONCEPT_FILE = "airlens_node_concept.glb";
export const BETA_FILE = "airlens_beta.glb";

// Kelompok node: casing dan modul konsep. colour hanya untuk penanda; warna asli dari GLB.
export const SHELL = ["enclosure_base", "enclosure_spine", "enclosure_sleeve", "enclosure_cap", "enclosure_shutter"];
export const MODULES = ["rpi5", "ai_hat_plus", "cam3_wide", "sen66", "co_b4_isb", "ads1115"];
export const BETA_CASE = ["beta_case_base", "beta_case_lid"];

// Diurai (bagian Exploded): geser Y (mm) untuk casing; modul ditarik `pull` mm ke arah pull_dir di placements.json.
// Kamera dan penutup lensa ikut cap. from/to = rentang progres bagian (0..1).
export const EXPLODE = {
  enclosure_cap: { dy: 160, from: 0.0, to: 0.4 },
  enclosure_shutter: { dy: 160, from: 0.0, to: 0.4 },
  cam3_wide: { dy: 160, from: 0.0, to: 0.4 },
  enclosure_sleeve: { dy: 90, from: 0.2, to: 0.6 },
  enclosure_base: { dy: -20, from: 0.3, to: 0.7 },
  modules: { pull: 40, from: 0.5, to: 0.95 },
};
export const SLEEVE_FADE = 0.15;      // selubung meredup setelah terangkat

// Penutup lensa: posisi di GLB = terbuka; tertutup = geser -26 mm di X (enclosure_concept.py, shutter()).
export const SHUTTER_CLOSE_X = -26;

// Sorotan bagian 5–8. keys = modul yang ditarik ke titik sorot; offset = geser relatif di titik sorot (mm);
// keep = node casing yang tetap terang. Kamera: az/el (derajat, 0 = depan +Z), dist (mm).
export const SPOTLIGHTS = [
  { id: "pi", keys: ["rpi5", "ai_hat_plus"], offset: { ai_hat_plus: [0, 48, 0] }, az: 35, el: 28, dist: 330 },
  { id: "cam", keys: ["cam3_wide"], keep: ["enclosure_shutter"], az: 20, el: 6, dist: 180 },
  { id: "sen66", keys: ["sen66"], keep: ["enclosure_sleeve"], az: 30, el: 12, dist: 300 },
  { id: "co", keys: ["co_b4_isb", "ads1115"], offset: { ads1115: [-52, 6, 0] }, az: 25, el: -16, dist: 300 },
];
export const BENCH = { y: 130, out: 150 };   // titik sorot: di depan menara, ke arah kamera

// Label penunjuk: [teks, titik dunia (mm) di posisi rakitan, geser label dx, dy (px)].
// group = kelompok tempat titik itu menempel (ikut bergerak bersamanya).
export const LABELS = {
  pi: [
    ["rpi5", "Active Cooler", [-6.0, 106.1, 6.0], -150, 40],
    ["rpi5", "GPIO header", [-0.5, 100.1, 27.9], -140, 80],
    ["ai_hat_plus", "PCIe to AI HAT+", [35.5, 107.6, 6.0], 140, -50],
  ],
  cam: [
    ["cam3_wide", "120° wide lens", [0.0, 177.2, 39.1], 130, -60],
    ["cam3_wide", "22-pin camera cable", [0.0, 157.5, 21.9], -150, 60],
  ],
  sen66: [
    ["sen66", "Air inlet", [-5.0, 52.8, 38.1], 130, -60],
    ["sen66", "Air outlet", [-38.0, 52.8, 38.1], -140, -50],
    ["enclosure_sleeve", "Gasketed funnel", [-22.5, 54.5, 41.0], -140, 70],
  ],
  co: [
    ["co_b4_isb", "Electrochemical cell", [24.0, 30.6, -8.0], 140, 60],
    ["co_b4_isb", "ISB amplifier", [24.0, 50.3, 6.0], 140, -50],
    ["ads1115", "ADS1115 ADC", [-18.0, 53.1, -22.0], -140, -50],
  ],
  // Beta: titik dihitung dari kotak batas node saat dimuat (atas-tengah kelompok).
  beta: [
    ["comp_esp32", "ESP32 DevKit V1", null, -140, -60],
    ["comp_mq_sensors", "4 MQ gas sensors", null, 130, -60],
    ["comp_resistors", "4 × 10 kΩ / 20 kΩ dividers", null, 40, 90],
  ],
};

// Kabel: warna dari prompt halaman produk (oranye 3,3 V, hitam GND, biru SDA, kuning SCL, hijau WE, ungu AE).
// Rute: SEN66 dan ADS1115 naik lewat celah grommet sekat ganda (belakang-kanan, x 38, z -27, Y 82–90) ke header
// GPIO di atas AI HAT+; ISB ke ADS1115. Pin dan rute ilustratif. Titik [group, x, y, z] menempel ke kelompoknya.
export const WIRE_COLOURS = { v33: 0xf08a24, gnd: 0x1b1f24, sda: 0x1f7ae0, scl: 0xd1a10f, we: 0x2ba84a, ae: 0x8e44c9 };
const G = (dz) => [["enclosure_spine", 38 - dz, 76, -27 + dz], ["enclosure_spine", 38 - dz, 86, -27 + dz], ["enclosure_spine", 38 - dz, 96, -27 + dz]];
const overHat = (dz) => [["enclosure_spine", 30 - dz, 124, -6], ["enclosure_spine", 24 - dz, 122, 22]];
export const WIRES = [
  // SEN66 (JST-GH di sisi belakang) -> grommet -> GPIO
  { colour: "v33", path: [["sen66", -2, 47.8, 9.7], ["enclosure_spine", 10, 62, -10], ...G(0), ...overHat(0), ["ai_hat_plus", 26.6, 115.7, 26.6]] },
  { colour: "gnd", path: [["sen66", -4, 47.8, 9.7], ["enclosure_spine", 10, 63, -12], ...G(1.5), ...overHat(1.5), ["ai_hat_plus", 21.5, 115.7, 29.2]] },
  { colour: "sda", path: [["sen66", -42, 47.8, 9.7], ["enclosure_spine", -10, 64, -14], ...G(3), ...overHat(3), ["ai_hat_plus", 24.1, 115.7, 26.6]] },
  { colour: "scl", path: [["sen66", -40, 47.8, 9.7], ["enclosure_spine", -8, 65, -16], ...G(4.5), ...overHat(4.5), ["ai_hat_plus", 21.5, 115.7, 26.6]] },
  // ADS1115 -> grommet -> GPIO (berbagi I2C)
  { colour: "v33", path: [["ads1115", -31.4, 50, -29.0], ["enclosure_spine", 0, 58, -33], ...G(-1.5), ...overHat(-1.5), ["ai_hat_plus", 26.6, 115.7, 26.6]] },
  { colour: "gnd", path: [["ads1115", -28.9, 50, -29.0], ["enclosure_spine", 0, 59, -34], ...G(-3), ...overHat(-3), ["ai_hat_plus", 16.5, 115.7, 26.6]] },
  { colour: "scl", path: [["ads1115", -26.4, 50, -29.0], ["enclosure_spine", 0, 60, -35], ...G(-4.5), ...overHat(-4.5), ["ai_hat_plus", 21.5, 115.7, 26.6]] },
  { colour: "sda", path: [["ads1115", -23.8, 50, -29.0], ["enclosure_spine", 0, 61, -36], ...G(-6), ...overHat(-6), ["ai_hat_plus", 24.1, 115.7, 26.6]] },
  // ISB (WE, AE) -> ADS1115 A0, A1: pendek, < 10 cm
  { colour: "we", path: [["co_b4_isb", 22, 55.1, -24.5], ["enclosure_spine", 4, 60, -30], ["ads1115", -16.2, 50, -29.0]] },
  { colour: "ae", path: [["co_b4_isb", 26, 55.1, -24.5], ["enclosure_spine", 6, 61, -31], ["ads1115", -13.6, 50, -29.0]] },
];

// Volume penanda (koordinat dunia, mm): [min, max]. Dari enclosure_concept.py: Z_BASE 12, sekat 82–90, Z_TOP 152.
export const VOLUMES = {
  cameraPocket: { min: [-24, 155, 28], max: [24, 200, 50], colour: 0x2ba8e0 },
  sensorZone: { min: [-56, 14, -42], max: [56, 80, 42], colour: 0x2ba8e0 },
  coolZone: { min: [-56, 14, -42], max: [56, 82, 42], colour: 0x2ba8e0, fill: 0.10 },
  divider: { min: [-56, 82, -42], max: [56, 90, 42], colour: 0x2ba8e0, fill: 0.22 },
  warmZone: { min: [-56, 90, -42], max: [56, 150, 42], colour: 0xf2994a, fill: 0.06 },
};

// Dua aliran udara (koordinat dunia, mm). Tiap jalur: titik-titik yang dilalui partikel.
// Udara ruangan: masuk kisi samping/depan-bawah, lewat sensor, keluar sisi seberang.
// Udara Pi: masuk kisi belakang-tengah (Y 96–124), lewat Active Cooler, keluar kisi atas-belakang cap.
export const AIRFLOW = {
  sensor: { colour: 0x2ba8e0, paths: [
    [[-95, 40, 0], [-50, 42, 0], [0, 48, 6], [50, 44, 0], [95, 40, 0]],
    [[95, 58, -10], [50, 58, -10], [0, 54, -4], [-50, 56, -10], [-95, 58, -10]],
    [[20, 22, 95], [24, 26, 44], [20, 40, 10], [55, 48, -10], [95, 50, -12]],
  ] },
  pi: { colour: 0xd9e2e8, paths: [
    [[0, 108, -95], [0, 108, -44], [-6, 112, -10], [-4, 140, -20], [0, 175, -28], [0, 225, -28]],
    [[-28, 104, -95], [-28, 104, -44], [-14, 110, -6], [-10, 142, -22], [-6, 176, -30], [-6, 226, -30]],
    [[28, 116, -95], [28, 116, -44], [14, 114, -4], [10, 142, -24], [6, 176, -30], [6, 226, -30]],
  ] },
};
