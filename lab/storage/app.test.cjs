"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const ui = require("./app.js");
const state = require("./state.json");

test("missing and nonfinite values never become zero prices or intervals", () => {
  for (const value of [null, undefined, NaN, Infinity, "12"]) {
    assert.equal(ui.format(value), "—");
    assert.equal(ui.sign(value), "—");
  }
  assert.equal(ui.sign(0), "0");
  assert.equal(ui.sign(-2), "−2");
  assert.equal(ui.day(null), "—");
});

test("release status changes at the scheduled boundary and rejects a late issue", () => {
  const cut = Date.parse(state.scheduled);
  assert.equal(ui.forecastStatus(state, cut - 1), "Recorded before release");
  assert.equal(ui.forecastStatus(state, cut), "Release time passed");
  assert.equal(ui.forecastStatus({...state,current:{...state.current,issued_at:state.scheduled}}, cut - 1), "Issue time unverified");
});

test("snapshot validation accepts empty history but rejects malformed observations", () => {
  assert.equal(ui.validateSnapshot(state), state);
  assert.doesNotThrow(() => ui.validateSnapshot({...state,recent:[],backtest:{n:0}}));
  assert.throws(() => ui.validateSnapshot({...state,recent:[{week:"2026-11-13",actual:null}]}));
  assert.throws(() => ui.validateSnapshot({...state,as_of:"bad date"}));
  assert.throws(() => ui.validateSnapshot({...state,current:{...state.current,forecast:null}}));
});

test("empty and single-week charts remain usable", () => {
  class Element {
    constructor(tag) { this.tag=tag; this.attrs={}; this.children=[]; this.clientWidth=300; this.clientHeight=225; }
    setAttribute(k,v) { this.attrs[k]=v; }
    append(n) { this.children.push(n); }
    replaceChildren() { this.children=[]; }
  }
  const graph=new Element("svg");
  global.document={getElementById:()=>graph,createElementNS:(_,tag)=>new Element(tag)};
  try {
    ui.chart([]);
    assert.equal(graph.children[0].textContent,"No replay observations");
    ui.chart([state.recent[0]]);
    assert.equal(graph.children.filter(n=>n.tag==="circle").length,3);
    assert.ok(!JSON.stringify(graph).includes("NaN"));
  } finally { delete global.document; }
});
