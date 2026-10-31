// render_svg.mjs in.svg out.png [width]
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { Resvg } = require("@resvg/resvg-js");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const [inp, outp, w] = process.argv.slice(2);
const svg = readFileSync(path.resolve(inp), "utf8");
const resvg = new Resvg(svg, {
  fitTo: { mode: "width", value: parseInt(w || "1920", 10) },
  font: {
    fontFiles: [path.join(HERE, "font.ttf")],
    loadSystemFonts: false,
    defaultFontFamily: "JetBrains Mono",
  },
});
writeFileSync(path.resolve(outp), resvg.render().asPng());
console.log("✔", outp);
