// Runs timing scenarios through the real lodash and Underscore implementations on a
// virtual clock and prints when each one invoked the wrapped function.
//
// Input (stdin): a JSON list of scenarios, each
//   {"id", "lib": "lodash" | "underscore", "kind": "debounce" | "throttle",
//    "wait", "leading", "trailing", "max_wait", "calls": [ms...], "end": ms}
// Output (stdout): {"<id>": {"runs": [[ms, call index], ...], "returns": [...]}}
//
// Timers due at or before a call's time fire before that call, in due order and then
// creation order; that is the order a real event loop gives timers that are already due.
"use strict";

const path = require("path");

let now = 0;
let sequence = 0;
let queue = [];

// Real clocks read far from zero; Underscore's throttle treats a reading below its
// wait as "ran at time 0", so the virtual clock reports an offset epoch.
const EPOCH = 1e12;
Date.now = () => EPOCH + now;
globalThis.setTimeout = (action, delay) => {
  const timer = { due: now + Math.max(0, Number(delay) || 0), seq: sequence++, action };
  queue.push(timer);
  return timer;
};
globalThis.clearTimeout = (timer) => {
  queue = queue.filter((t) => t !== timer);
};

const here = __dirname;
const lodashDebounce = require(path.join(here, "lodash", "debounce.js"));
const lodashThrottle = require(path.join(here, "lodash", "throttle.js"));
const underscore = require(path.join(here, "underscore", "underscore-node-f.cjs"));

function advance(to) {
  for (;;) {
    queue.sort((a, b) => a.due - b.due || a.seq - b.seq);
    const next = queue[0];
    if (next === undefined || next.due > to) break;
    queue.shift();
    now = next.due;
    next.action();
  }
  now = to;
}

function build(s, func) {
  if (s.lib === "lodash" && s.kind === "debounce") {
    const options = { leading: s.leading, trailing: s.trailing };
    if (s.max_wait !== null) options.maxWait = s.max_wait;
    return lodashDebounce(func, s.wait, options);
  }
  if (s.lib === "lodash") {
    return lodashThrottle(func, s.wait, { leading: true, trailing: s.trailing });
  }
  if (s.kind === "debounce") {
    if (s.max_wait !== null || s.leading === s.trailing) throw new Error(s.id + ": no such option");
    return underscore.debounce(func, s.wait, s.leading);
  }
  return underscore.throttle(func, s.wait, { leading: true, trailing: s.trailing });
}

function run(s) {
  now = 0;
  sequence = 0;
  queue = [];
  const runs = [];
  const fn = build(s, (index) => {
    runs.push([now, index]);
    return index;
  });
  const returns = [];
  s.calls.forEach((time, index) => {
    advance(time);
    const value = fn(index);
    returns.push(value === undefined ? null : value);
  });
  advance(s.end);
  return { runs, returns };
}

let input = "";
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const out = {};
  for (const s of JSON.parse(input)) out[s.id] = run(s);
  process.stdout.write(JSON.stringify(out));
});
