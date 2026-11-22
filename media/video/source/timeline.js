// Linimasa video: durasi tiap adegan (detik) dan parameter sebagai fungsi waktu t.
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const ramp = (t, a, b) => clamp((t - a) / (b - a));
const scenes = [
  { id: "01_room_intro", scene: "room", dur: 8, o: (t) => ({ smoke: ramp(t, 4, 8) * 0.6, cam: [3.4 - t * 0.06, 2.3, 2.4 - t * 0.05],
      kicker: "Meet Pak Dengklek", text: t < 4.2 ? "The city app says<br>the air is fine." : "The city app says the air is fine.<br><em>His room says otherwise.</em>", textA: t < 4.2 ? ramp(t, 0.6, 1.3) : 1 }) },
  { id: "02_room_detect", scene: "room", dur: 6, o: (t) => ({ smoke: 0.6 + ramp(t, 0, 2) * 0.35, cam: [2.9, 2.2, 1.9], camOn: ramp(t, 1.4, 1.6),
      flash: Math.max(0, 1 - Math.abs(t - 1.8) * 6), badge: ramp(t, 1.8, 2.3), alert: ramp(t, 3.4, 4.2), look: ramp(t, 4.2, 5.2),
      kicker: "Sensors trigger the camera", text: "Smoke detected.<br><b>One event photo.</b>", textA: ramp(t, 0.3, 1) }) },
  { id: "03_dashboard", scene: "dash", dur: 7, o: (t) => ({ smoke: ramp(t, 0, 2.5), alert: ramp(t, 2.6, 3.4), snap: ramp(t, 4, 4.6) }) },
  { id: "04_room_close", scene: "room", dur: 4, o: (t) => ({ smoke: 0.95, close: ramp(t, 0.5, 2.5), look: 1, alert: 1 - ramp(t, 2.5, 3.5), cam: [2.4, 2.0, 1.2], target: [0.6, 1.6, -2.5],
      kicker: "Alert on the dashboard", text: "Window closed.<br><b>Air recovering.</b>", textA: ramp(t, 0.8, 1.5) }) },
  { id: "05_invisible_gas", scene: "gas", dur: 7, o: (t) => ({ gas: ramp(t, 1, 4), alert: ramp(t, 4, 4.8) }) },
  { id: "06_city", scene: "city", dur: 7, o: (t) => ({ pull: ramp(t, 0, 4.5),
      kicker: "Hyperlocal", text: "City station: 18 km away.<br><b>AirLens node: 2 m away.</b>", textA: ramp(t, 3.4, 4.2), textBottom: 640 }) },
  { id: "07_hardware", scene: "node", dur: 9, o: (t) => ({ explode: ramp(t, 0.6, 3.2), kicker: "", text: "" }) },
  { id: "08_fusion", scene: "fusion", dur: 7, o: (t) => ({ flow: ramp(t, 0, 3), cam: ramp(t, 3, 4.5) }) },
  { id: "09_shap", scene: "shap", dur: 7, o: (t) => ({ grow: ramp(t, 0.3, 4) }) },
  { id: "10_site", scene: "site", dur: 5, o: () => ({}) },
  { id: "11_mlops", scene: "loop", dur: 5, o: () => ({}) },
  { id: "12_end", scene: "end", dur: 7, o: () => ({}) },
];
const FADE = 0.3;
const total = scenes.reduce((a, s) => a + s.dur, 0);
module.exports = { scenes, total, FADE, clamp };
