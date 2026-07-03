/* Copyright: Ankitects Pty Ltd and contributors
   License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */
/* Node harness for the desktop/mobile scoring parity test. Loads the browser
   scoring port (vantage_addon/web/mobile_scoring.js) in a vm with a minimal
   window/document shim, then computes the pure numeric transforms for the inputs
   in argv[3] and writes the results as JSON to stdout. scoring_parity_test.py
   compares these against the Python core (anki.vantage.scoring). No DOM needed.
   Named .cjs because the repo package.json is "type": "module". */
"use strict";
const fs = require("fs");
const vm = require("vm");

const jsPath = process.argv[2];
const inputPath = process.argv[3];
const code = fs.readFileSync(jsPath, "utf8");
const inp = JSON.parse(fs.readFileSync(inputPath, "utf8"));

// Shim the two browser globals the IIFE assigns to; everything else (Math, JSON,
// Set, ...) comes from node's own globals via runInThisContext.
const shim =
  "var window = {}; var document = { addEventListener: function(){}, " +
  "getElementById: function(){ return null; } };\n";
vm.runInThisContext(shim + code + "\nglobalThis.__PARITY_S = window.__vantageScoring;");
const S = globalThis.__PARITY_S;
if (!S) {
  process.stderr.write("mobile_scoring.js did not expose window.__vantageScoring\n");
  process.exit(2);
}

const out = {
  thetaToScale: inp.thetas.map((t) => S.thetaToScale(t)),
  mapAbilityToScale: inp.abilities.map((a) => S.mapAbilityToScale(a)),
  irtProb: inp.triples.map(([t, a, b]) => S.irtProb(t, a, b)),
  irtInformation: inp.triples.map(([t, a, b]) => S.irtInformation(t, a, b)),
  irtEstimate: inp.itemSets.map((items) => {
    const e = S.irtEstimate(items);
    return [e.theta, e.theta_sd, e.information];
  }),
};
process.stdout.write(JSON.stringify(out));
