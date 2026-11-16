/* Federal Circuit Panels dashboard. Every number is counted here, in the browser, from
   data/archive.json (one row per decision and one per AI-coded issue) and data/calendar.json.
   The counting rules are written out in CLAUDE.md ("Methodology: dashboard statistics") and, for readers,
   in methodology.html. Two modes: "session" (a case on the court's calendar) and "free" (any panel, no case). */
"use strict";

const MIN_N = 10;          // fewer decided votes than this: shown grey, never compared with the court
const Z = 1.96;            // 95% Wilson interval for "differs from the court"
const DRILL_PAGE = 25;
const F = { date: 0, name: 1, appeals: 2, origin: 3, r36: 4, prec: 5, prose: 6, panel: 7, author: 8,
            argued: 9, days: 10, enbanc: 11, sup: 12, pdf: 13 };
const R = { d: 0, code: 1, ct: 2, fav: 3, disp: 4, dis: 5 };
const DISP_BUCKET = ["aff", "rev", "vac", "vac", "rev", "part", "dism", "vac", "other"];
const DISP_NAME = { aff: "affirmed", rev: "reversed", vac: "vacated/remanded", part: "affirmed in part", dism: "dismissed", other: "other" };
const VIS = "VISITING";

let A, CAL;                 // archive, calendar
let jkey = [];              // judge index -> grouping key (visiting judges share one key)
let issueByCode = {};
const quoteCache = {};
const S = { m: "session", date: "", s: "", j: ["", "", ""], a: "", ct: -1, i: "", y: 2015, ps: 1, st: 1 };
let drillState = null;

/* ---------- small helpers ---------- */
const $ = (id) => document.getElementById(id);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false)
    e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
const pct = (x) => (x === null || isNaN(x)) ? "–" : Math.round(100 * x) + "%";
function median(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function wilson(k, n) {
  if (!n) return [0, 1];
  const p = k / n, z2 = Z * Z, den = 1 + z2 / n;
  const c = (p + z2 / (2 * n)) / den, hw = Z * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / den;
  return [c - hw, c + hw];
}
function titleName(n) {
  return n.replace(" (visiting)", "").toLowerCase().replace(/(^|[\s'-])([a-z])/g, (m, a, b) => a + b.toUpperCase());
}
function judgeLabel(key) { return key === VIS ? "Visiting judges" : titleName(key); }
function caseTitle(n) {
  const small = new Set(["v", "of", "and", "the", "in", "re", "for", "llc", "inc", "co", "corp", "ltd", "us"]);
  return n.split(" ").map((w, i) => {
    if (w === "v") return "v.";
    if (["llc", "inc", "ltd", "corp", "co"].includes(w)) return w === "llc" ? "LLC" : w[0].toUpperCase() + w.slice(1) + ".";
    if (w === "us") return "U.S.";
    if (i > 0 && small.has(w)) return w;
    return w.charAt(0).toUpperCase() + w.slice(1);
  }).join(" ");
}
const shortSide = (s) => (s || "").replace(/\s*\(.*?\)\s*/g, " ").split(/ [\/,] | or /)[0].trim();
const fmtDate = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
function todayET() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

/* ---------- state in the URL, so a view can be shared ---------- */
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("m") === "free") S.m = "free";
  if (p.get("date")) S.date = p.get("date");
  if (p.get("s")) S.s = p.get("s");
  if (p.get("j")) S.j = (p.get("j").split(",").concat(["", "", ""])).slice(0, 3);
  if (p.get("a")) S.a = p.get("a");
  if (p.get("ct")) S.ct = +p.get("ct");
  if (p.get("i")) S.i = p.get("i");
  if (p.get("y")) S.y = +p.get("y");
  if (p.get("ps")) S.ps = +p.get("ps");
  if (p.get("st")) S.st = +p.get("st");
}
function writeHash() {
  const free = S.m === "free";   // "any panel" links carry no session or case
  const p = new URLSearchParams(free ? { m: "free", j: S.j.join(","), ct: S.ct, i: S.i, y: S.y, ps: S.ps, st: S.st }
    : { date: S.date, s: S.s, j: S.j.join(","), a: S.a, ct: S.ct, i: S.i, y: S.y, ps: S.ps, st: S.st });
  history.replaceState(null, "", "#" + p.toString());
}

/* ---------- filters ---------- */
const sinceIso = () => S.y + "-01-01";
function keysOf(d) { return d[F.panel].map((j) => jkey[j]); }
/* Decisions used for judge statistics: not en banc, not superseded, has a panel, in the year range. */
function judgeDecision(d, useProSe) {
  if (d[F.enbanc] || d[F.sup] || d[F.date] < sinceIso()) return false;
  if (useProSe && S.ps && d[F.prose]) return false;
  return true;
}
function countIn(keys, key) { let n = 0; for (const k of keys) if (k === key) n++; return n; }
function containsAll(keys, want) {
  const need = {};
  for (const w of want) need[w] = (need[w] || 0) + 1;
  return Object.entries(need).every(([k, n]) => countIn(keys, k) >= n);
}

/* ---------- section 1: calendar ---------- */
function sessionsOn(date) { return CAL.sessions.filter((s) => s.date === date); }
function currentSession() { return S.m === "free" ? null : sessionsOn(S.date).find((s) => s.panel === S.s) || null; }
function currentCase() { const s = currentSession(); return s ? s.cases.find((c) => c.appeal === S.a) || null : null; }

function renderMode() {
  const free = S.m === "free";
  $("mode-session").checked = !free; $("mode-free").checked = free;
  $("session-section").hidden = free;
  $("free-note").hidden = !free;
}
function renderCalendar() {
  if (S.m === "free") return;
  const dates = [...new Set(CAL.sessions.map((s) => s.date))];
  if (!dates.includes(S.date)) {
    const t = todayET();
    S.date = dates.find((d) => d >= t) || dates[dates.length - 1] || "";
  }
  const ds = $("date");
  ds.replaceChildren(...dates.map((d) => h("option", { value: d, selected: d === S.date }, fmtDate(d) + (d === todayET() ? " (today)" : ""))));
  const ss = sessionsOn(S.date);
  if (!ss.some((s) => s.panel === S.s)) S.s = ss.length ? ss[0].panel : "";
  $("session").replaceChildren(...ss.map((s) => h("option", { value: s.panel, selected: s.panel === S.s },
    `Panel ${s.panel} · ${s.time.replace("A.M.", " a.m.").replace("P.M.", " p.m.")} · Courtroom ${s.courtroom} (${s.cases.length} cases)`)));
  const sess = currentSession();
  const t = $("cases");
  t.replaceChildren(h("thead", {}, h("tr", {}, h("th", {}, "Appeal"), h("th", {}, "From"), h("th", {}, "Case"), h("th", {}, "Argument"))));
  const tb = h("tbody");
  for (const c of sess ? sess.cases : []) {
    tb.append(h("tr", { "data-appeal": c.appeal, class: c.appeal === S.a ? "selected" : null, tabindex: 0,
      onclick: () => selectCase(c), onkeydown: (e) => { if (e.key === "Enter") selectCase(c); } },
      h("td", { class: "nowrap" }, c.appeal), h("td", {}, c.origin), h("td", {}, c.name),
      h("td", { class: "muted nowrap" }, c.argued ? "argued" : "on the briefs")));
  }
  t.append(tb);
  $("cal-source").textContent = CAL.calendars.map((c) => c.source.split("/").pop() + (c.revised ? ` (revised ${c.revised})` : "") +
    (c.archived ? " (no longer posted by the court; kept as last read)" : "")).join(", ") + `; read ${CAL.read}.`;
}

/* Case type guessed from the calendar's origin code, using the most common AI case type for that origin. */
function guessCaseType(c) {
  const names = A.case_types.map((t) => t.name);
  const exParte = names.findIndex((n) => n.startsWith("Patent: ex parte"));
  const ptab = names.findIndex((n) => n.startsWith("Patent: PTAB"));
  if (c.origin === "PTO") return /^in re\b/i.test(c.name) ? exParte : ptab;
  const list = A.origin_case_types[c.origin] || [];
  const fallback = { MSPB: "Federal employment", CAVC: "Veterans", BCA: "Government contracts", ITC: "Patent: district",
                     DCT: "Patent: district", CIT: "Trade: antidumping", CFC: "Other Court of Federal Claims" }[c.origin];
  const pick = list[0] || names.find((n) => fallback && n.startsWith(fallback)) || names[names.length - 1];
  return names.indexOf(pick);
}
function selectCase(c) {
  S.a = c.appeal;
  S.ct = guessCaseType(c);
  S.i = "";
  renderAll();
}

/* ---------- section 2: panel pickers and sit-together ---------- */
let pickerOptions = [];
function buildPickerOptions() {
  const last = {};
  for (const d of A.decisions) for (const j of d[F.panel]) {
    const k = jkey[j];
    if (!last[k] || d[F.date] > last[k]) last[k] = d[F.date];
  }
  const latest = A.meta.latest_decision, yearAgo = (+latest.slice(0, 4) - 1) + latest.slice(4);
  const fc = Object.keys(last).filter((k) => k !== VIS).sort((a, b) => last[b].localeCompare(last[a]) || a.localeCompare(b));
  const recent = fc.filter((k) => last[k] >= yearAgo), older = fc.filter((k) => last[k] < yearAgo);
  pickerOptions = [
    { group: "Sat in the past year", items: recent.map((k) => [k, titleName(k)]) },
    { group: "Not in the past year", items: older.map((k) => [k, `${titleName(k)} (last ${last[k].slice(0, 4)})`]) },
    { group: "Other", items: [[VIS, "Visiting judge (district or other court)"]] },
  ];
}
/* Panel known from the court's decisions: all cases in a session go to the same panel, and every decision's PDF
   names it, so once any case in a past session is decided (on or after the session date) its panel is known.
   Returns null, or { panels: [{ keys, names, from: [decisions] }] } (more than one panel = a judge was replaced
   for some case, e.g. a recusal). */
function decidedPanel(sess) {
  if (!sess) return null;
  const appeals = new Set(sess.cases.map((c) => c.appeal));
  const byPanel = new Map();
  for (const d of A.decisions) {
    if (d[F.date] < sess.date || d[F.enbanc] || d[F.panel].length < 2) continue;
    if (!d[F.appeals].split("; ").some((a) => appeals.has(a))) continue;
    const id = d[F.panel].map((j) => A.judges[j]).sort().join("|");
    if (!byPanel.has(id)) byPanel.set(id, { keys: keysOf(d), names: d[F.panel].map((j) => titleName(A.judges[j]) + (A.judges[j].endsWith("(visiting)") ? " (visiting)" : "")), from: [] });
    byPanel.get(id).from.push(d);
  }
  return byPanel.size ? { panels: [...byPanel.values()] } : null;
}
const sameJudges = (a, b) => a.filter(Boolean).slice().sort().join("|") === b.slice().sort().join("|");
function listNames(xs) { return xs.length < 3 ? xs.join(" and ") : xs.slice(0, -1).join(", ") + ", and " + xs[xs.length - 1]; }
/* Fill the pickers with the decided panel when the user has not chosen judges. */
function autofillPanel() {
  const kp = decidedPanel(currentSession());
  if (kp && kp.panels.length === 1 && kp.panels[0].keys.length === 3 && S.j.every((x) => !x)) S.j = kp.panels[0].keys.slice();
}
/* Before moving to another session, clear judges that were only the old session's decided panel. */
function clearAutofill() {
  const kp = decidedPanel(currentSession());
  if (kp && kp.panels.length === 1 && sameJudges(S.j, kp.panels[0].keys)) S.j = ["", "", ""];
}
function panelFromDecisions() {
  const kp = decidedPanel(currentSession());
  return kp && kp.panels.length === 1 && sameJudges(S.j, kp.panels[0].keys) ? kp.panels[0] : null;
}
function decisionNote(p) {
  const d = p.from[0], more = p.from.length - 1;
  return `the court's decision in ${d[F.appeals].split("; ")[0]} (${d[F.r36] ? "Rule 36 judgment" : "opinion"}, ${fmtDate(d[F.date])})` +
    (more ? ` and ${more} other decision${more > 1 ? "s" : ""} from this session` : "");
}

/* Where the judges' names came from. Until the morning panel reader exists, always the user.
   The reader will set PANEL_FROM_COURT = { read: "<time>" } for sessions whose panel it found. */
const PANEL_FROM_COURT = null;
function oneHourBefore(t) {           // "10:00A.M." -> "9:00 a.m."
  const m = /^(\d+):(\d+)([AP])/.exec(t || "");
  if (!m) return "";
  let hr = (+m[1] % 12) + (m[3] === "P" ? 12 : 0) - 1;
  if (hr < 0) hr += 24;
  return `${hr % 12 || 12}:${m[2]} ${hr < 12 ? "a.m." : "p.m."}`;
}
function panelTiming() {
  const sess = currentSession();
  if (!sess) return "";
  const today = todayET(), when = oneHourBefore(sess.time);
  if (sess.date > today) return `The court has not posted this panel yet: judges' names go up on its daily schedule about one hour before the session (around ${when} on ${fmtDate(sess.date)}).`;
  if (sess.date === today) return `The court posts this panel's names on its daily schedule about one hour before the session (around ${when} today).`;
  return "This session has passed and none of its cases has been decided yet. The panel will be filled in from the first decision; the court's daily schedule shows only the current day's panels.";
}
function renderPanelSource() {
  const el = $("panel-source");
  if (S.m === "free") {
    el.replaceChildren(h("strong", {}, "Any panel – judges chosen by you. "),
      "Not tied to an argument session or case: try any combination of judges, case type, and issue.");
    return;
  }
  if (PANEL_FROM_COURT) { el.replaceChildren(`Judges read from the court's daily schedule at ${PANEL_FROM_COURT.read}.`); return; }
  const fromDec = panelFromDecisions();
  if (fromDec) {
    el.replaceChildren(h("strong", {}, "Panel from the court's decisions: "), `${listNames(fromDec.names)}, as named in ${decisionNote(fromDec)}.`);
    return;
  }
  const kp = decidedPanel(currentSession());
  let known = "";
  if (kp && kp.panels.length === 1) known = ` The court's decisions in this session name the panel as ${listNames(kp.panels[0].names)}.`;
  else if (kp) known = " The decided cases in this session name different panels (a judge may have been replaced for a case): " +
    kp.panels.map((p) => `${listNames(p.names)} (${p.from.map((d) => d[F.appeals].split("; ")[0]).join(", ")})`).join("; ") + ".";
  el.replaceChildren(h("strong", {}, "Judges entered by you – not from the court. "), known ? known.trim() : panelTiming());
}
function renderPickers() {
  renderPanelSource();
  const box = $("judge-pickers");
  box.replaceChildren(...[0, 1, 2].map((i) => {
    const sel = h("select", { "aria-label": `Judge ${i + 1}`, onchange: (e) => { S.j[i] = e.target.value; drillState = null; renderAll(); } },
      h("option", { value: "" }, "— choose —"),
      pickerOptions.map((g) => h("optgroup", { label: g.group }, g.items.map(([k, t]) => h("option", { value: k, selected: S.j[i] === k }, t)))));
    return h("label", {}, `Judge ${i + 1}`, sel);
  }));
}
function renderTogether() {
  const box = $("together");
  const js = S.j.filter(Boolean);
  if (js.length < 2) { box.replaceChildren(h("p", { class: "hint" }, "Choose at least two judges to see how often they have sat together.")); return; }
  const pool = A.decisions.filter((d) => !d[F.enbanc] && !d[F.sup] && d[F.panel].length && d[F.date] >= sinceIso());
  const combos = [];
  for (let a = 0; a < 3; a++) for (let b = a + 1; b < 3; b++) if (S.j[a] && S.j[b]) combos.push([S.j[a], S.j[b]]);
  if (js.length === 3) combos.push(js);
  const tiles = combos.map((want) => {
    const hits = pool.filter((d) => (want.length === 2 || d[F.panel].length === 3) && containsAll(keysOf(d), want));
    const r36 = hits.filter((d) => d[F.r36]).length;
    const last = hits.length ? hits[hits.length - 1][F.date] : null;
    return h("div", { class: "tile" },
      h("div", { class: "who" }, want.length === 3 ? "All three together" : want.map(judgeLabel).join(" & ")),
      h("div", { class: "big" }, hits.length),
      h("div", { class: "small muted" }, `decisions since ${S.y}` + (hits.length ? ` (${r36} Rule 36) · last ${last}` : "")));
  });
  box.replaceChildren(h("div", { class: "together" }, tiles),
    h("p", { class: "hint" }, "Counts decisions issued by a panel that included these judges (written opinions and Rule 36 judgments; " +
      "consolidated appeals decided together count once). En banc decisions and decisions whose PDF names no panel are left out; " +
      "two-judge panels count for pairs, not for all three." + (js.includes(VIS) ? " \"Visiting judges\" counts any visiting judge." : "")));
}

/* ---------- section 3: judges ---------- */
function originSet(origin) { return origin === "PTO" ? ["PTO", "TTAB"] : [origin]; }
function renderJudges() {
  const keys = [...new Set(S.j.filter(Boolean))];
  const t = $("judges");
  const c = currentCase();
  const pool = A.decisions.filter((d) => judgeDecision(d, true));
  const opinions = pool.filter((d) => !d[F.r36] && d[F.panel].length);
  // Court-wide comparisons
  const seats = opinions.reduce((s, d) => s + d[F.panel].length, 0);
  const signed = opinions.filter((d) => d[F.author] >= 0);
  const courtShare = seats ? signed.length / seats : null;
  const courtDays = (p) => median(signed.filter((d) => d[F.prec] === p && d[F.days] !== null).map((d) => d[F.days]));
  const r36Pool = (list) => list.filter((d) => {
    if (!c) return true;
    const okO = originSet(c.origin).includes(A.origins[d[F.origin]]);
    const okA = c.argued ? d[F.argued] !== "" : d[F.argued] === "";
    return okO && okA;
  });
  const courtR = r36Pool(pool);
  const courtR36 = courtR.length ? courtR.filter((d) => d[F.r36]).length / courtR.length : null;
  const r36Label = c ? `Rule 36 rate: ${c.origin} cases ${c.argued ? "argued" : "decided on the briefs"}` : "Rule 36 rate (all cases)";

  t.replaceChildren(h("thead", {}, h("tr", {},
    h("th", {}, "Judge"), h("th", { class: "num" }, "Decisions"),
    h("th", { class: "num" }, "Wrote the opinion"), h("th", { class: "num" }, "Days to opinion: precedential"),
    h("th", { class: "num" }, "nonprecedential"), h("th", { class: "num" }, r36Label))));
  const tb = h("tbody");
  for (const k of keys) {
    const sat = pool.filter((d) => keysOf(d).includes(k));
    const ops = sat.filter((d) => !d[F.r36]);
    const mine = ops.filter((d) => d[F.author] >= 0 && jkey[d[F.author]] === k);
    const days = (p) => mine.filter((d) => d[F.prec] === p && d[F.days] !== null).map((d) => d[F.days]);
    const dP = days(1), dN = days(0);
    const rp = r36Pool(sat);
    const r36 = rp.filter((d) => d[F.r36]).length;
    tb.append(h("tr", {},
      h("td", {}, judgeLabel(k)),
      h("td", { class: "num" }, sat.length),
      h("td", { class: "num" }, ops.length ? `${pct(mine.length / ops.length)} of ${ops.length}` : "–"),
      h("td", { class: "num" }, dP.length ? `${median(dP)} (n=${dP.length})` : "–"),
      h("td", { class: "num" }, dN.length ? `${median(dN)} (n=${dN.length})` : "–"),
      h("td", { class: "num" }, rp.length ? `${pct(r36 / rp.length)} of ${rp.length}` : "–")));
  }
  tb.append(h("tr", { class: "court" },
    h("td", {}, h("strong", {}, "Whole court")),
    h("td", { class: "num" }, pool.length),
    h("td", { class: "num" }, `${pct(courtShare)} per seat`),
    h("td", { class: "num" }, courtDays(1) ?? "–"),
    h("td", { class: "num" }, courtDays(0) ?? "–"),
    h("td", { class: "num" }, pct(courtR36))));
  t.append(tb);
  $("judges-note").textContent = (keys.length ? "" : "Choose judges above. ") +
    "Wrote the opinion = share of the written panel opinions they sat on that they signed (the rest are by colleagues or per curiam). " +
    "Days to opinion = median days from oral argument to a signed opinion they wrote (only cases with a known argument date). " +
    "Rule 36 rate = Rule 36 judgments as a share of all decisions in cases they sat on, matched to the selected case's origin and argued/on-the-briefs status." +
    (S.ps ? " Cases with a pro se party are left out." : "");
}

/* ---------- section 4: issue votes ---------- */
const GROUP_LETTER = (name) => name.startsWith("Patent") || name.startsWith("Interferences") ? "P" :
  name.startsWith("Trademark") ? "T" : name.startsWith("Veterans") ? "V" : name.startsWith("Federal employment") ? "E" :
  name.startsWith("Government contracts") ? "C" : name.startsWith("Other Court of Federal Claims") ? "F" :
  name.startsWith("Trade") ? "R" : "";
function sideNames(ct) {
  const t = A.case_types[ct];
  return [shortSide(t.side_a) || "Side A", shortSide(t.side_b) || "Side B"];
}
function labelsFor(code, ct) {
  const [sa, sb] = sideNames(ct);
  const i = issueByCode[code];
  if (!i || code.startsWith("X") || !i.side_a_label) return [`for ${sa.toLowerCase()}`, `for ${sb.toLowerCase()}`];
  return [`${i.side_a_label} (${sa.toLowerCase()})`, `${i.side_b_label} (${sb.toLowerCase()})`];
}
function renderIssuePickers() {
  const cs = $("ctype");
  if (S.ct < 0 || S.ct >= A.case_types.length) S.ct = 0;
  cs.replaceChildren(...A.case_types.map((t, i) => h("option", { value: i, selected: i === S.ct }, t.name)));
  const letter = GROUP_LETTER(A.case_types[S.ct].name);
  const counts = {};
  for (const r of A.rulings) if (r[R.ct] === S.ct) counts[r[R.code]] = (counts[r[R.code]] || 0) + 1;
  const codes = A.issues.filter((i) => (letter && i.code[0] === letter) || i.code[0] === "X");
  if (!codes.some((i) => i.code === S.i)) {
    const best = codes.map((i) => i.code).sort((a, b) => (counts[b] || 0) - (counts[a] || 0))[0];
    S.i = best || codes[0].code;
  }
  const groups = [...new Set(codes.map((i) => i.group))];
  $("issue").replaceChildren(...groups.map((g) => h("optgroup", { label: g },
    codes.filter((i) => i.group === g).map((i) => h("option", { value: i.code, selected: i.code === S.i },
      `${i.code} · ${i.issue} — ${counts[i.code] || 0} rulings`)))));
  const iss = issueByCode[S.i];
  $("issue-covers").textContent = iss ? `${iss.issue}: ${iss.covers}` : "";
  const c = currentCase(), sess = currentSession();
  $("case-line").textContent = c ? `Case: ${c.appeal} ${c.name} (${c.origin}, ${c.argued ? "argued" : "on the briefs"}), Panel ${sess.panel}. ` +
    "The case type is a guess from the origin and case name; change it if it is wrong." +
    (PANEL_FROM_COURT || !S.j.some(Boolean) ? "" : panelFromDecisions() ? " Judges: from the court's decisions in this session." : " Judges: entered by you, not from the court.") :
    (S.m === "free" ? "Any panel, no case: choose the case type and the issue." :
     "No case selected: choose the case type yourself, or click a case above.");
}

function tally(rulings, key) {
  const t = { a: 0, b: 0, m: 0, u: 0, disp: {}, rows: [] };
  for (const r of rulings) {
    const d = A.decisions[r[R.d]];
    let seats;
    if (key === null) seats = [null];
    else { seats = d[F.panel].filter((j) => jkey[j] === key); if (!seats.length) continue; }
    for (const j of seats) {
      let f = r[R.fav];
      const dissent = j !== null && r[R.dis].includes(j);
      if (dissent) f = f === 0 ? 1 : f === 1 ? 0 : 3;
      t["abmu"[f]]++;
      const b = DISP_BUCKET[r[R.disp]];
      t.disp[b] = (t.disp[b] || 0) + 1;
      t.rows.push({ r, f, dissent });
    }
  }
  t.n = t.a + t.b + t.m;
  return t;
}
function voteRow(label, t, court, isCourt, key, labels, which) {
  const few = t.n < MIN_N;
  const share = (x) => t.n ? x / t.n : 0;
  const bar = h("div", { class: "bar", role: "img",
    "aria-label": `${pct(share(t.a))} ${labels[0]}, ${pct(share(t.m))} mixed, ${pct(share(t.b))} ${labels[1]}` },
    t.a ? h("span", { class: "a", style: `width:${100 * share(t.a)}%`, title: `${t.a} ${labels[0]}` }) : null,
    t.m ? h("span", { class: "m", style: `width:${100 * share(t.m)}%`, title: `${t.m} mixed` }) : null,
    t.b ? h("span", { class: "b", style: `width:${100 * share(t.b)}%`, title: `${t.b} ${labels[1]}` }) : null,
    !isCourt && court.n ? h("span", { class: "tick", style: `left:calc(${100 * court.a / court.n}% - 1px)`, title: `Court: ${pct(court.a / court.n)} ${labels[0]}` }) : null);
  let signal = "";
  if (!isCourt && !few && court.n) {
    const [lo, hi] = wilson(t.a, t.n), cr = court.a / court.n;
    if (lo > cr) signal = `▲ voted ${labels[0]} more often than the court`;
    else if (hi < cr) signal = `▼ voted ${labels[0]} less often than the court`;
    else signal = "within the court's range";
  } else if (!isCourt && few) signal = t.n ? "too few votes to compare" : "";
  const disp = ["aff", "rev", "vac", "part", "dism", "other"].filter((k) => t.disp[k]).map((k) => `${t.disp[k]} ${k}`).join(" · ");
  return h("tr", { class: [isCourt ? "court" : "", few && !isCourt ? "few" : ""].join(" ").trim() || null,
    "data-judge": key ?? "COURT", tabindex: 0,
    onclick: () => openDrill(which, key), onkeydown: (e) => { if (e.key === "Enter") openDrill(which, key); } },
    h("td", {}, label, bar),
    h("td", { class: "num" }, pct(t.n ? t.a / t.n : null)),
    h("td", { class: "num" }, pct(t.n ? t.m / t.n : null)),
    h("td", { class: "num" }, pct(t.n ? t.b / t.n : null)),
    h("td", { class: "num" }, t.n + (t.u ? ` (+${t.u})` : "")),
    h("td", { class: "small muted" }, disp),
    h("td", { class: "small signal" }, signal));
}
function issueRulings(codes) {
  return A.rulings.filter((r) => codes.includes(r[R.code]) && (!S.st || r[R.ct] === S.ct) && judgeDecision(A.decisions[r[R.d]], true));
}
function voteTable(el, codes, labels, which) {
  const rs = issueRulings(codes);
  const court = tally(rs, null);
  el.replaceChildren(h("thead", {}, h("tr", {},
    h("th", {}, "Judge"), h("th", { class: "num" }, labels[0]), h("th", { class: "num" }, "mixed"),
    h("th", { class: "num" }, labels[1]), h("th", { class: "num" }, "votes (+unclear)"), h("th", {}, "court's disposition"), h("th", {}, "compared with the court"))));
  const tb = h("tbody");
  for (const k of [...new Set(S.j.filter(Boolean))]) tb.append(voteRow(judgeLabel(k), tally(rs, k), court, false, k, labels, which));
  tb.append(voteRow("Whole court (rulings)", court, court, true, null, labels, which));
  el.append(tb);
}
function renderVotes() {
  const labels = labelsFor(S.i, S.ct);
  const [sa, sb] = sideNames(S.ct);
  $("legend").replaceChildren(
    h("span", {}, h("i", { style: "background:var(--side-a)" }), labels[0]),
    h("span", {}, h("i", { style: "background:var(--mixed)" }), "mixed (some claims or counts each way)"),
    h("span", {}, h("i", { style: "background:var(--side-b)" }), labels[1]),
    h("span", {}, h("i", { class: "tick" }), "whole-court share"));
  voteTable($("votes"), [S.i], labels, "issue");
  const iss = issueByCode[S.i];
  const gcodes = A.issues.filter((i) => i.group === iss.group).map((i) => i.code);
  $("group-title").textContent = `All "${iss.group}" issues together (${gcodes.length} codes), by side`;
  voteTable($("group-votes"), gcodes, [`for ${sa.toLowerCase()}`, `for ${sb.toLowerCase()}`], "group");
  if (drillState) renderDrill();
}

/* ---------- drill-down: the cases behind a row ---------- */
function openDrill(which, key) { drillState = { which, key, shown: DRILL_PAGE }; renderDrill(); $("drill").scrollIntoView({ behavior: "smooth", block: "start" }); }
async function renderDrill() {
  const box = $("drill");
  if (!drillState) { box.replaceChildren(); return; }
  const iss = issueByCode[S.i];
  const codes = drillState.which === "issue" ? [S.i] : A.issues.filter((i) => i.group === iss.group).map((i) => i.code);
  const labels = drillState.which === "issue" ? labelsFor(S.i, S.ct) : sideNames(S.ct).map((s) => `for ${s.toLowerCase()}`);
  const t = tally(issueRulings(codes), drillState.key);
  const rows = t.rows.sort((x, y) => A.decisions[y.r[R.d]][F.date].localeCompare(A.decisions[x.r[R.d]][F.date]));
  const need = [...new Set(rows.slice(0, drillState.shown).map((x) => x.r[R.code]))].filter((c) => !quoteCache[c]);
  await Promise.all(need.map((c) => fetch(`data/quotes/${c}.json`).then((r) => r.ok ? r.json() : {}).then((q) => { quoteCache[c] = q; }).catch(() => { quoteCache[c] = {}; })));
  const idxOf = new Map(A.rulings.map((r, i) => [r, i]));
  const who = drillState.key === null ? "the whole court" : judgeLabel(drillState.key);
  const items = rows.slice(0, drillState.shown).map(({ r, f, dissent }) => {
    const d = A.decisions[r[R.d]];
    const q = (quoteCache[r[R.code]] || {})[idxOf.get(r)] || ["", ""];
    const outcome = f === 0 ? labels[0] : f === 1 ? labels[1] : f === 2 ? "mixed" : "other/unclear";
    return h("div", { class: "case" },
      h("div", {}, h("span", { class: "muted nowrap" }, d[F.date] + " "), h("a", { href: d[F.pdf], target: "_blank", rel: "noopener" }, caseTitle(d[F.name])),
        h("span", { class: "muted" }, ` (${d[F.appeals]})`),
        h("span", { class: "tag" }, r[R.code]), h("span", { class: "tag" }, d[F.prec] ? "precedential" : "nonprecedential"),
        d[F.prose] ? h("span", { class: "tag" }, "pro se") : null),
      h("div", { class: "small" }, h("strong", {}, (drillState.key === null ? "Ruling: " : dissent ? "Dissented: " : "Voted: ") + outcome),
        ` · court's disposition: ${A.dispositions[r[R.disp]]}`),
      q[0] ? h("p", { class: "quote" }, q[0]) : null,
      q[1] ? h("p", { class: "quote" }, "“" + q[1] + "”") : null);
  });
  box.replaceChildren(
    h("h3", {}, `Cases behind the row for ${who} (${rows.length}), newest first`),
    ...items,
    rows.length > drillState.shown ? h("p", {}, h("button", { class: "link", onclick: () => { drillState.shown += 100; renderDrill(); } }, "Show more")) : null,
    h("p", {}, h("button", { class: "link", onclick: () => { drillState = null; renderDrill(); } }, "Close")));
}

/* ---------- wiring ---------- */
function renderAll() {
  renderMode(); renderCalendar(); autofillPanel(); renderPickers(); renderTogether(); renderJudges(); renderIssuePickers(); renderVotes(); writeHash();
}
async function main() {
  readHash();
  try {
    [A, CAL] = await Promise.all([fetch("data/archive.json").then((r) => r.json()), fetch("data/calendar.json").then((r) => r.json())]);
  } catch (e) {
    $("status").textContent = "Could not load the data files.";
    return;
  }
  jkey = A.judges.map((n) => n.endsWith("(visiting)") ? VIS : n);
  for (const i of A.issues) issueByCode[i.code] = i;
  $("status").textContent = `Decisions through ${A.meta.latest_decision} · calendar read ${CAL.read} · ${A.meta.classification}`;
  if (A.meta.test_data) { const b = $("test-banner"); b.hidden = false; b.textContent = "Development build: issue statistics use only the 50-case test sample. Do not rely on them."; }
  const years = []; for (let y = +A.meta.latest_decision.slice(0, 4); y >= 2015; y--) years.push(y);
  $("since").replaceChildren(...years.map((y) => h("option", { value: y, selected: y === S.y }, y)));
  $("pro-se").checked = !!S.ps; $("same-type").checked = !!S.st;
  const setMode = (m) => { S.m = m; drillState = null; renderAll(); window.scrollTo({ top: 0 }); };
  $("mode-session").onchange = () => setMode("session");
  $("mode-free").onchange = () => setMode("free");
  $("date").onchange = (e) => { clearAutofill(); S.date = e.target.value; S.s = ""; S.a = ""; drillState = null; renderAll(); };
  $("session").onchange = (e) => { clearAutofill(); S.s = e.target.value; S.a = ""; drillState = null; renderAll(); };
  $("since").onchange = (e) => { S.y = +e.target.value; renderAll(); };
  $("pro-se").onchange = (e) => { S.ps = e.target.checked ? 1 : 0; renderAll(); };
  $("same-type").onchange = (e) => { S.st = e.target.checked ? 1 : 0; renderAll(); };
  $("ctype").onchange = (e) => { S.ct = +e.target.value; S.i = ""; drillState = null; renderAll(); };
  $("issue").onchange = (e) => { S.i = e.target.value; drillState = null; renderAll(); };
  buildPickerOptions();
  renderAll();
}
main();
