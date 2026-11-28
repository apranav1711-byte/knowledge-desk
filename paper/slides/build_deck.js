// Builds paper/slides/Knowledge-Desk.pptx. Every number is read from paper/tables/numbers.tex (generated from the experiment results).
// Run:  cd D:\Accenture-tools\deck && node D:\Accenture\paper\slides\build_deck.js
const path = require("path");
const fs = require("fs");
const TOOLS = "D:/Accenture-tools/deck/node_modules/";
const pptxgen = require(TOOLS + "pptxgenjs");
const React = require(TOOLS + "react");
const ReactDOMServer = require(TOOLS + "react-dom/server");
const sharp = require(TOOLS + "sharp");
const fa = require(TOOLS + "react-icons/fa");
const { applyTheme } = require("C:/Users/ashiv/AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/97749d07-984e-41c4-be45-a3a11d652c01/b53029e2-abb1-4fe9-919f-170e7ca99dfe/skills/pptx/scripts/apply_theme.js");

const HERE = __dirname;
const OUT = path.join(HERE, "Knowledge-Desk.pptx");

// ---------- numbers from the paper's generated macros ----------
const N = {};
for (const m of fs.readFileSync(path.join(HERE, "..", "tables", "numbers.tex"), "utf8").matchAll(/^\\newcommand\{\\(\w+)\}\{(.*)\}\s*$/gm)) N[m[1]] = m[2].replace(/\{,\}/g, ",");
const num = (k) => { if (!(k in N)) throw new Error("missing macro " + k); return N[k]; };
const pct = (k) => `${Math.round(parseFloat(num(k)))}%`;
const pct1 = (k) => `${parseFloat(num(k)).toFixed(1)}%`;
const totalQ = parseInt(num("NAnswerable").replace(/,/g, "")) + parseInt(num("NUnanswerable"));

// ---------- theme ----------
const THEME = {
  name: "Knowledge Desk",
  headFontFace: "Cambria", bodyFontFace: "Calibri",
  colors: { dk1: "1F1F1F", lt1: "FFFFFF", dk2: "14142B", lt2: "F4F3F8", accent1: "F26A1B", accent2: "8FA0FF", accent3: "1B9E77",
            accent4: "7570B3", accent5: "D63A3A", accent6: "9A9AA8", hlink: "3B4CCA", folHlink: "7570B3" },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.title = "Knowledge Desk";
pres.author = "Pranav Aggarwal";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

// ---------- layouts ----------
pres.defineSlideMaster({ title: "Dark title", background: { color: HEX.dk2 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.7, y: 1.55, w: 8.6, h: 1.1, fontSize: 44, bold: true, color: C.background1, align: "left", valign: "top", margin: 0 }, text: "" } }] });
pres.defineSlideMaster({ title: "Content", background: { color: HEX.lt1 }, slideNumber: { x: 9.2, y: 5.2, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent6, align: "right" },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 8.8, h: 0.8, fontSize: 32, bold: true, color: C.text2, align: "left", valign: "top", margin: 0 }, text: "" } }] });

// ---------- helpers ----------
const shadow = () => ({ type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.12 });
async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
function iconBadge(slide, img, x, y, d, fill, name) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name + " badge" });
  const p = d * 0.28;
  slide.addImage({ data: img, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, altText: name, objectName: name });
}
function card(slide, x, y, w, h, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.background2 }, line: { color: HEX.lt2, width: 0 }, shadow: shadow(), objectName: name });
}
const txt = (slide, text, o) => slide.addText(text, { isTextBox: true, margin: 0, fontFace: THEME.bodyFontFace, color: HEX.dk1, valign: "top", ...o });
const bigStat = (slide, x, y, w, value, label, color, name) => {
  txt(slide, value, { x, y, w, h: 0.9, fontSize: 48, bold: true, fontFace: THEME.headFontFace, color, objectName: name + " value" });
  txt(slide, label, { x, y: y + 0.95, w, h: 0.7, fontSize: 14, color: HEX.dk1, objectName: name + " label" });
};
const content = (title, section) => { const s = pres.addSlide({ masterName: "Content", sectionTitle: section }); s.addText(title, { placeholder: "title" }); return s; };

(async () => {
  const I = {
    shield: await icon(fa.FaUserShield, "FFFFFF"), quote: await icon(fa.FaQuoteLeft, "FFFFFF"), clip: await icon(fa.FaClipboardCheck, "FFFFFF"),
    search: await icon(fa.FaSearch, "FFFFFF"), lock: await icon(fa.FaLock, "FFFFFF"), history: await icon(fa.FaHistory, "FFFFFF"),
    file: await icon(fa.FaFileAlt, "FFFFFF"), check: await icon(fa.FaCheckCircle, "FFFFFF"),
  };

  pres.addSection({ title: "Context" });
  // 1 -- title
  {
    const s = pres.addSlide({ masterName: "Dark title", sectionTitle: "Context" });
    s.addText("Knowledge Desk", { placeholder: "title" });
    txt(s, "A secure enterprise knowledge assistant that quotes its sources and respects who is allowed to read what", { x: 0.7, y: 2.75, w: 7.4, h: 1.0, fontSize: 20, color: HEX.accent2, objectName: "Subtitle" });
    txt(s, "Pranav Aggarwal  |  RV College of Engineering  |  Experiential Learning project", { x: 0.7, y: 4.7, w: 8.6, h: 0.4, fontSize: 14, color: HEX.lt2, objectName: "Byline" });
    s.addNotes("Introduce the project in one sentence: an assistant for company documents that never makes up an answer and never shows a person a document they are not cleared for. The rest of the talk shows how it is built, how we tested it, and what we learned, including what did not work.");
  }
  // 2 -- the problem
  {
    const s = content("Enterprise assistants are hard to trust", "Context");
    const rows = [
      [I.lock, HEX.accent1, "Authorisation", "A salary band is for HR and an acquisition plan is for administrators. Access checks that happen after retrieval can leak."],
      [I.quote, HEX.accent4, "Trust", "Generative models can write fluent text that no document supports, and users cannot tell which parts are real."],
      [I.history, HEX.accent3, "Accountability", "Operators must later show what was asked and answered, and detect tampering with that record."],
    ];
    rows.forEach(([img, col, head, body], i) => {
      const y = 1.45 + i * 1.18;
      card(s, 0.6, y, 8.8, 1.0, "Problem card " + (i + 1));
      iconBadge(s, img, 0.85, y + 0.17, 0.66, col, head + " icon");
      txt(s, head, { x: 1.8, y: y + 0.14, w: 7.3, h: 0.32, fontSize: 18, bold: true, color: HEX.dk2, objectName: head + " heading" });
      txt(s, body, { x: 1.8, y: y + 0.48, w: 7.3, h: 0.45, fontSize: 14, objectName: head + " text" });
    });
    txt(s, "Problem statement: an AI-powered enterprise knowledge assistant, provided by an industry professional.", { x: 0.6, y: 5.0, w: 8.4, h: 0.3, fontSize: 11, color: HEX.accent6, objectName: "Source caption" });
    s.addNotes("Three problems that classroom RAG demos usually skip. First, who is allowed to see what. Second, why users can trust an answer. Third, being able to prove later what happened. Our project is built around these three.");
  }
  // 3 -- design principle
  {
    const s = content("Our design: quote, cite, or abstain", "Context");
    const cards = [
      [I.quote, HEX.accent1, "No text generation", "Answers are sentences or table rows copied from the documents, each with a citation to its page."],
      [I.shield, HEX.accent4, "Role-aware search", "The search only ever considers passages the asking person's role may read."],
      [I.clip, HEX.accent3, "Tamper-evident log", "Every question and change is chained with hashes, so edits and deletions are detectable."],
    ];
    cards.forEach(([img, col, head, body], i) => {
      const x = 0.6 + i * 3.0;
      card(s, x, 1.5, 2.8, 3.1, head);
      iconBadge(s, img, x + 0.25, 1.75, 0.8, col, head + " icon");
      txt(s, head, { x: x + 0.25, y: 2.75, w: 2.3, h: 0.4, fontSize: 18, bold: true, color: HEX.dk2, objectName: head + " heading" });
      txt(s, body, { x: x + 0.25, y: 3.2, w: 2.3, h: 1.3, fontSize: 14, objectName: head + " text" });
    });
    s.addNotes("Our deliberate choice: the system never generates text. That removes invented text, but as we will see it does not by itself guarantee a correct answer, and studying that gap is a main finding.");
  }

  pres.addSection({ title: "System" });
  // 4 -- architecture
  {
    const s = content("How it works", "System");
    const box = (x, y, w, label, fill, name, tc) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.7, rectRadius: 0.06, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name });
      txt(s, label, { x, y, w, h: 0.7, fontSize: 13, bold: true, color: tc || "FFFFFF", align: "center", valign: "middle", objectName: name + " text" });
    };
    const arrow = (x, y, w) => s.addShape(pres.shapes.RIGHT_ARROW, { x, y: y + 0.2, w, h: 0.3, fill: { color: HEX.accent6 }, line: { color: HEX.accent6, width: 0 }, objectName: "Arrow" });
    txt(s, "Ingestion (once per document)", { x: 0.6, y: 1.3, w: 5, h: 0.3, fontSize: 14, bold: true, color: HEX.accent4, objectName: "Ingestion label" });
    box(0.6, 1.7, 1.9, "Upload\n8 file formats", HEX.dk2, "Upload");        arrow(2.55, 1.7, 0.4);
    box(3.0, 1.7, 1.9, "Parse and chunk\ntables kept intact", HEX.dk2, "Parse"); arrow(4.95, 1.7, 0.4);
    box(5.4, 1.7, 1.9, "Embed\nbge-small model", HEX.dk2, "Embed");         arrow(7.35, 1.7, 0.4);
    box(7.8, 1.7, 1.6, "Store\nvectors + text", HEX.dk2, "Store");
    txt(s, "Each question", { x: 0.6, y: 2.8, w: 5, h: 0.3, fontSize: 14, bold: true, color: HEX.accent1, objectName: "Query label" });
    box(0.6, 3.2, 1.9, "Question\n+ user role", HEX.dk2, "Question");               arrow(2.55, 3.2, 0.4);
    box(3.0, 3.2, 1.9, "Role pre-filter\nonly readable passages", HEX.accent3, "Role filter"); arrow(4.95, 3.2, 0.4);
    box(5.4, 3.2, 1.9, "Hybrid search\nkeyword + meaning", HEX.dk2, "Search");    arrow(7.35, 3.2, 0.4);
    box(7.8, 3.2, 1.6, "Answer guard\nquote or abstain", HEX.accent3, "Guard");
    box(3.0, 4.35, 4.3, "Hash-chained audit log (every question and change)", HEX.accent4, "Audit log");
    txt(s, "Green stages are the security-relevant ones.", { x: 7.5, y: 4.5, w: 1.9, h: 0.5, fontSize: 11, color: HEX.accent6, objectName: "Legend" });
    s.addNotes("Documents are parsed with their structure, split into passages, embedded and stored once. For each question the role filter comes first, so restricted passages are never even scored, then keyword and semantic search are combined, then the guard decides whether the evidence is enough to quote.");
  }
  // 5 -- access levels
  {
    const s = content("Five access levels, four roles", "System");
    const head = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 }, align: "center", fontSize: 13 } });
    const yes = { text: "Yes", options: { color: HEX.accent3, bold: true, align: "center", fontSize: 13 } };
    const no = { text: "-", options: { color: HEX.accent6, align: "center", fontSize: 13 } };
    const lab = (t) => ({ text: t, options: { bold: true, fontSize: 13, color: HEX.dk1 } });
    s.addTable([
      [{ text: "Document level", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 }, fontSize: 13 } }, head("Employee"), head("Manager"), head("HR"), head("Admin")],
      [lab("Public, General Internal"), yes, yes, yes, yes],
      [lab("Management"), no, yes, no, yes],
      [lab("HR Confidential"), no, no, yes, yes],
      [lab("Restricted"), no, no, no, yes],
    ], { x: 0.6, y: 1.45, w: 8.8, colW: [3.2, 1.4, 1.4, 1.4, 1.4], rowH: 0.52, border: { type: "solid", pt: 0.75, color: "D9D8E2" }, valign: "middle", objectName: "Access table" });
    txt(s, "Managers and HR have separate confidential areas. Only admins read everything. The role is checked inside the database query and again after retrieval.", { x: 0.6, y: 4.3, w: 8.8, h: 0.7, fontSize: 14, objectName: "Access note" });
    s.addNotes("This is the lattice. Note that a manager cannot read HR documents and HR cannot read management documents: it is not a simple ladder. Changing a document's level instantly changes who can find it.");
  }
  // 6 -- demo screens
  {
    const s = content("The assistant in action", "System");
    s.addImage({ path: path.join(HERE, "img", "demo_answer.jpg"), x: 1.2, y: 1.25, w: 7.6, h: 7.6 * 590 / 1500, altText: "Assistant answer with a citation and the evidence panel", objectName: "Answer screenshot", shadow: shadow() });
    txt(s, "Each answer is quoted, cited, and backed by the evidence panel.", { x: 1.2, y: 4.35, w: 7.6, h: 0.35, fontSize: 14, objectName: "Caption" });
    txt(s, "Live demo (3 min): the same question as Employee, Manager and HR.", { x: 1.2, y: 4.8, w: 7.6, h: 0.35, fontSize: 16, bold: true, color: HEX.accent1, objectName: "Demo prompt" });
    s.addNotes("Show the demo video or run it live. The key moment: the same question gets an answer for a manager and \"not enough information\" for an employee.");
  }

  pres.addSection({ title: "Results" });
  // 7 -- evaluation setup
  {
    const s = content("How we tested it", "Results");
    const stats = [[num("NDocs"), "synthetic policy documents across the five levels"], [num("NFacts"), "facts, many near-duplicates differing only in the entity"], [totalQ.toLocaleString("en-US"), "questions: answerable, reworded, synonym-phrased and unanswerable"], [num("NSeeds"), "random corpora, so results carry error bars"]];
    stats.forEach(([v, l], i) => {
      const x = 0.6 + i * 2.25;
      card(s, x, 1.5, 2.05, 2.2, "Stat card " + (i + 1));
      txt(s, v, { x: x + 0.15, y: 1.65, w: 1.75, h: 0.8, fontSize: 40, bold: true, fontFace: THEME.headFontFace, color: HEX.accent1, objectName: "Stat " + (i + 1) });
      txt(s, l, { x: x + 0.15, y: 2.5, w: 1.75, h: 1.1, fontSize: 13, objectName: "Stat label " + (i + 1) });
    });
    txt(s, "We ran the real implementation: parser, chunker, embeddings, database, retrieval and answer guard. The data is synthetic because real company documents are confidential.", { x: 0.6, y: 4.0, w: 8.8, h: 0.9, fontSize: 16, objectName: "Setup note" });
    s.addNotes("Be upfront: the benchmark is synthetic and templated. We designed it with near-duplicate documents on purpose, because that is where enterprise retrieval actually struggles.");
  }
  // 8 -- access control result
  {
    const s = content("Result 1: access control works", "Results");
    bigStat(s, 0.6, 1.45, 2.8, pct("LeakNoAcl"), "of unauthorised questions leaked restricted content with no access control", HEX.accent5, "Leak without ACL");
    bigStat(s, 3.6, 1.45, 2.0, pct("LeakPre"), "leaked with role-aware filtering", HEX.accent3, "Leak with filter");
    bigStat(s, 0.6, 3.35, 2.8, `${num("AuditDetected")} of ${num("AuditTrials")}`, "audit-log tampering attempts detected", HEX.accent4, "Audit detection");
    s.addImage({ path: path.join(HERE, "img", "demo_audit.jpg"), x: 5.9, y: 1.6, w: 3.5, h: 3.5 * 235 / 640, altText: "Security self-test result: 0 leaks in 52 trials", objectName: "Audit screenshot", shadow: shadow() });
    txt(s, "The built-in security test probes every document as every role.", { x: 5.9, y: 3.1, w: 3.5, h: 0.6, fontSize: 14, objectName: "Audit caption" });
    s.addNotes(`Without access control, ${pct("TopFiveNoAcl")} of unauthorised questions had a restricted passage in the top five results. With role-aware filtering, none did. Honest note: pre-filtering and post-filtering gave almost the same accuracy (${pct1("AccPre")} vs ${pct1("AccPost")}), so the benefit of pre-filtering is structural: restricted text is never even scored.`);
  }
  // 9 -- retrieval chart
  {
    const s = content("Result 2: hybrid search is the most robust", "Results");
    const labels = ["Questions using the document's words", "Synonym-phrased questions"];
    s.addChart(pres.charts.BAR, [
      { name: "Keyword (BM25)", labels, values: [parseFloat(num("RKwBmOne")), parseFloat(num("RSynBmOne"))] },
      { name: "Semantic only", labels, values: [parseFloat(num("RKwDnOne")), parseFloat(num("RSynDnOne"))] },
      { name: "Hybrid (ours)", labels, values: [parseFloat(num("RKwHyOne")), parseFloat(num("RSynHyOne"))] },
    ], { x: 0.6, y: 1.3, w: 5.9, h: 3.8, barDir: "col", barGrouping: "clustered", chartColors: [HEX.accent1, HEX.accent4, HEX.accent3],
         showTitle: true, title: "Correct passage ranked first (%)", titleFontSize: 14, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
         showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
         catAxisLabelColor: HEX.dk1, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", valAxisLabelColor: HEX.accent6, valAxisLabelFontSize: 10, valAxisLabelFontFace: "+mn-lt",
         valAxisMinVal: 0, valAxisMaxVal: 80, valGridLine: { color: "E6E5EE", size: 0.75 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: HEX.dk1 });
    txt(s, "Keyword search wins when users repeat the document's words.", { x: 6.8, y: 1.5, w: 2.6, h: 0.9, fontSize: 14, objectName: "Takeaway 1" });
    txt(s, "Hybrid wins when they rephrase, and is never the worst.", { x: 6.8, y: 2.6, w: 2.6, h: 0.9, fontSize: 14, bold: true, color: HEX.accent3, objectName: "Takeaway 2" });
    txt(s, "So it is the safest default, not a universal winner.", { x: 6.8, y: 3.7, w: 2.6, h: 0.9, fontSize: 14, objectName: "Takeaway 3" });
    s.addNotes("Average over five corpora. Keyword search is hard to beat when the question repeats the document's wording, which matches published benchmark findings. Semantic search helps when the user uses different words, and combining them is the most robust.");
  }
  // 10 -- honest finding: guard
  {
    const s = content("Result 3: faithful is not always correct", "Results");
    s.addChart(pres.charts.BAR, [
      { name: "Deployed guard", labels: ["Wrong-entity answers", "False answers to unanswerable questions"], values: [parseFloat(num("GSAllWrong")), parseFloat(num("GSAllFalse"))] },
      { name: "Entity-span guard (proposed)", labels: ["Wrong-entity answers", "False answers to unanswerable questions"], values: [parseFloat(num("GEAllWrong")), parseFloat(num("GEAllFalse"))] },
    ], { x: 0.6, y: 1.3, w: 5.6, h: 3.8, barDir: "col", barGrouping: "clustered", chartColors: [HEX.accent5, HEX.accent3],
         showTitle: true, title: "Share of questions (%)", titleFontSize: 14, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
         showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
         catAxisLabelColor: HEX.dk1, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", valAxisLabelColor: HEX.accent6, valAxisLabelFontSize: 10, valAxisLabelFontFace: "+mn-lt",
         valAxisMinVal: 0, valAxisMaxVal: 100, valGridLine: { color: "E6E5EE", size: 0.75 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: HEX.dk1 });
    txt(s, "Copying a sentence about the wrong entity is faithful but wrong.", { x: 6.5, y: 1.5, w: 2.9, h: 0.9, fontSize: 14, objectName: "Finding 1" });
    txt(s, "Requiring the entity named in the question to appear in the quoted sentence fixes most of it.", { x: 6.5, y: 2.6, w: 2.9, h: 1.1, fontSize: 14, objectName: "Finding 2" });
    txt(s, `Correct answers stay at ${pct("GEAllCorr")}: removed answers become abstentions.`, { x: 6.5, y: 3.85, w: 2.9, h: 0.9, fontSize: 14, bold: true, color: HEX.accent3, objectName: "Finding 3" });
    s.addNotes("This is our most important honest finding. Because the system only quotes, it never invents text, but with many near-duplicate documents it sometimes quotes the wrong entity's sentence. A simple entity check cuts wrong answers and false answers sharply without losing correct ones. It needs validation on real documents.");
  }

  pres.addSection({ title: "Wrap-up" });
  // 11 -- limits and next steps
  {
    const s = content("Limits and next steps", "Wrap-up");
    const col = (x, head, color, items, name) => {
      card(s, x, 1.4, 4.3, 3.5, name);
      txt(s, head, { x: x + 0.25, y: 1.6, w: 3.8, h: 0.4, fontSize: 20, bold: true, color, objectName: name + " heading" });
      items.forEach((t, i) => txt(s, t, { x: x + 0.25, y: 2.2 + i * 0.68, w: 3.8, h: 0.6, fontSize: 14, objectName: name + " item " + (i + 1) }));
    };
    col(0.6, "Limits", HEX.accent5, ["Synthetic, templated benchmark", "No comparison with an LLM-based pipeline", "Entity guard needs testing on real documents", "No user study yet"], "Limits");
    col(5.1, "Next steps", HEX.accent3, ["Add an LLM layer that must cite its sources", "Evaluate on real public policy documents", "Role-partitioned indexes for larger collections", "Anchor the audit log outside the system"], "Next steps");
    s.addNotes("Name the limits before anyone asks. The synthetic benchmark is the biggest one. Next steps are what we would do with more time.");
  }
  // 12 -- close
  {
    const s = pres.addSlide({ masterName: "Dark title", sectionTitle: "Wrap-up" });
    s.addText("Thank you", { placeholder: "title" });
    txt(s, "Answers your team can trust, from documents they are allowed to see.", { x: 0.7, y: 2.75, w: 7.4, h: 0.8, fontSize: 20, color: HEX.accent2, objectName: "Closing line" });
    txt(s, "Paper: Knowledge Desk, IEEE format (project repository)   |   Questions?", { x: 0.7, y: 4.7, w: 8.6, h: 0.4, fontSize: 14, color: HEX.lt2, objectName: "Closing footer" });
  }

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
