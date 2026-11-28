"""results.json + results_formats.json -> LaTeX tables (paper/tables) and figures (paper/figures). No hand-typed numbers."""
import json, statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT_T, OUT_F = HERE.parent / "tables", HERE.parent / "figures"
OUT_T.mkdir(exist_ok=True); OUT_F.mkdir(exist_ok=True)
R = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
FMT = json.loads((HERE / "results_formats.json").read_text(encoding="utf-8")) if (HERE / "results_formats.json").exists() else None
S = R["seeds"]
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.grid": True, "grid.alpha": .3, "figure.dpi": 200})
COL = {"lexical": "#d95f02", "dense": "#7570b3", "hybrid": "#1b9e77"}


def ms(get, pct=True, digits=1):
    v = [get(s) for s in S]
    m, sd = st.mean(v), (st.stdev(v) if len(v) > 1 else 0.0)
    k = 100 if pct else 1
    return f"{m * k:.{digits}f}\\,$\\pm$\\,{sd * k:.{digits}f}", m


def write(name, text):
    (OUT_T / name).write_text(text, encoding="utf-8")


# ---------------- Table: retrieval ablation by query type
rows = []
for typ, label in (("keyword", "Keyword-aligned queries"), ("synonym", "Synonym queries")):
    rows.append(f"\\multicolumn{{5}}{{l}}{{\\emph{{{label}}}}}\\\\")
    for mode, name in (("lexical", "BM25 only"), ("dense", "Dense only"), ("hybrid", "Hybrid (RRF)")):
        c = [ms(lambda s, m=mode, t=typ, k=k: s["E1_by_query_type"][m][t][k])[0] for k in ("recall@1", "recall@3", "recall@5")]
        mrr = ms(lambda s, m=mode, t=typ: s["E1_by_query_type"][m][t]["mrr"], pct=False, digits=3)[0]
        rows.append(f"{name} & {c[0]} & {c[1]} & {c[2]} & {mrr}\\\\")
write("retrieval.tex", "\\begin{tabular}{lrrrr}\n\\toprule\nRetriever & R@1 (\\%) & R@3 (\\%) & R@5 (\\%) & MRR\\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---------------- Table: access control
rows = []
for key, name in (("no_acl", "No access control"), ("postfilter", "Post-filtering"), ("prefilter", "Pre-filtering (ours)")):
    acc = ms(lambda s, k=key: s["E2_access"][k]["auth_correct"] / s["E2_access"][k]["auth_total"])[0]
    leak = ms(lambda s, k=key: s["E2_access"][k]["unauth_leak"] / s["E2_access"][k]["unauth_total"])[0]
    expo = ms(lambda s, k=key: s["E2_access"][k]["unauth_hits_leak"] / s["E2_access"][k]["unauth_total"])[0]
    rows.append(f"{name} & {acc} & {leak} & {expo}\\\\")
n_un = sum(s["E2_access"]["prefilter"]["unauth_total"] for s in S)
write("access.tex", "\\begin{tabular}{lrrr}\n\\toprule\nSystem & Correct (\\%) & Leaked answers (\\%) & Top-5 exposure (\\%)\\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---------------- Table: answer guard
rows = []
base = lambda f: (lambda s: S and s["E3_guard"]["0.55"][f])
for label, getter in (("Standard guard (deployed)", lambda f, v: (lambda s: s["E3_guard"]["0.55"][f]) if v == "all" else None),):
    pass
def row(label, tau):
    cells = []
    for f in ("correct", "wrong_entity", "false_answer_unanswerable"):
        cells.append(ms(lambda s, f=f: (s["E3_guard"]["0.55"][f] if tau is None else s["E3_strict_guard"][f"{tau}|all"][f]))[0])
    return f"{label} & " + " & ".join(cells) + "\\\\"
rows.append(row("Standard guard (deployed)", None))
for tau in (0.5, 0.7, 0.8, 0.9, 1.0):
    rows.append(row(f"+ sentence coverage $\\geq {tau}$", tau))
write("guard.tex", "\\begin{tabular}{lrrr}\n\\toprule\nGuard & Correct (\\%) & Wrong entity (\\%) & False answers (\\%)\\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---------------- Table: formats
if FMT:
    names = {"md": "Markdown", "txt": "Plain text", "html": "HTML", "docx": "Word (.docx)", "xlsx": "Excel (.xlsx)", "csv": "CSV", "pptx": "PowerPoint (.pptx)", "pdf": "PDF"}
    rows = [f"{names[k]} & {v['facts']} & {100 * v['extraction_rate']:.1f} & {100 * v['recall_at_1']:.1f} & {100 * v['recall_at_3']:.1f}\\\\" for k, v in FMT.items()]
    write("formats.tex", "\\begin{tabular}{lrrrr}\n\\toprule\nFormat & Facts & Extracted (\\%) & R@1 (\\%) & R@3 (\\%)\\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---------------- Table: audit
if "E7_audit" in R:
    rows = [f"{v['records']:,} & {v['verify_seconds']:.2f} & {v['detected']}/{v['tamper_trials']}\\\\" for v in R["E7_audit"].values()]
    write("audit.tex", "\\begin{tabular}{rrr}\n\\toprule\nRecords & Verify time (s) & Tampering detected\\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---------------- Figure: k sweep (pre vs post)
ks = ["1", "2", "3", "5", "10"]
fig, ax = plt.subplots(figsize=(3.4, 2.3))
for name, ls, c in (("prefilter", "-", "#1b9e77"), ("postfilter", "--", "#d95f02")):
    m = [st.mean(s["E2_ksweep"][name][k] for s in S) * 100 for k in ks]
    ax.plot([int(k) for k in ks], m, ls, marker="o", ms=3, color=c, label="Pre-filtering" if name == "prefilter" else "Post-filtering")
ax.set_xlabel("Retrieved passages $k$"); ax.set_ylabel("Correct answers, authorised (%)"); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(OUT_F / "ksweep.pdf"); plt.close(fig)

# ---------------- Figure: guard trade-off
taus = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
fig, ax = plt.subplots(figsize=(3.4, 2.5))
for var, c, mk in (("keyword", "#1b9e77", "o"), ("synonym", "#7570b3", "s")):
    x = [st.mean(s["E3_strict_guard"][f"{t}|{var}"]["false_answer_unanswerable"] for s in S) * 100 for t in taus]
    y = [st.mean(s["E3_strict_guard"][f"{t}|{var}"]["correct"] for s in S) * 100 for t in taus]
    ax.plot(x, y, "-", marker=mk, ms=3, color=c, label=f"{var.capitalize()} queries")
    for t, xi, yi in zip(taus, x, y):
        if t in (0.0, 0.8, 1.0): ax.annotate(f"{t}", (xi, yi), textcoords="offset points", xytext=(3, 3), fontsize=6)
ax.set_xlabel("False answers on unanswerable questions (%)"); ax.set_ylabel("Correct answers (%)"); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(OUT_F / "guard_tradeoff.pdf"); plt.close(fig)

# ---------------- Figure: retrieval bars
fig, ax = plt.subplots(figsize=(3.4, 2.3)); w = .25
for i, mode in enumerate(("lexical", "dense", "hybrid")):
    for j, typ in enumerate(("keyword", "synonym")):
        v = [s["E1_by_query_type"][mode][typ]["recall@1"] * 100 for s in S]
        ax.bar(j + (i - 1) * w, st.mean(v), w, yerr=st.stdev(v) if len(v) > 1 else 0, color=COL[mode], capsize=1.5,
               label={"lexical": "BM25", "dense": "Dense", "hybrid": "Hybrid"}[mode] if j == 0 else None)
ax.set_xticks([0, 1]); ax.set_xticklabels(["Keyword-aligned", "Synonym"]); ax.set_ylabel("Recall@1 (%)"); ax.legend(frameon=False, ncol=3, fontsize=6)
fig.tight_layout(); fig.savefig(OUT_F / "retrieval.pdf"); plt.close(fig)

# ---------------- Figure: scaling
if "E5_scaling" in R:
    sizes = sorted(int(k) for k in R["E5_scaling"])
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    for role, ls in (("employee", "-"), ("admin", "--")):
        ax.plot(sizes, [R["E5_scaling"][str(n)][role]["p50_ms"] for n in sizes], ls, marker="o", ms=3, label=f"{role} p50")
        ax.plot(sizes, [R["E5_scaling"][str(n)][role]["p95_ms"] for n in sizes], ls, marker="^", ms=3, alpha=.6, label=f"{role} p95")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("Indexed passages"); ax.set_ylabel("Retrieval latency (ms)"); ax.legend(frameon=False, fontsize=6)
    fig.tight_layout(); fig.savefig(OUT_F / "scaling.pdf"); plt.close(fig)

exec(compile((HERE / "artifacts_extra.py").read_text(encoding="utf-8"), "artifacts_extra.py", "exec"))

# ---------------- summary numbers for the text
facts = {"seeds": len(S), "docs": S[0]["docs"], "chunks_mean": round(st.mean(s["chunks"] for s in S)), "facts": S[0]["facts"],
         "answerable": S[0]["answerable"], "unanswerable": S[0]["unanswerable"],
         "faithfulness": [s["E4_faithfulness"] for s in S]}
(HERE / "summary.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
print("artifacts written")
