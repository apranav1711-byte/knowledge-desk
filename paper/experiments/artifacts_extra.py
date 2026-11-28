# Executed by make_artifacts.py (shares its namespace): guard tables/figure and the LaTeX macros for every number in the text.
BS = "\\"  # a single backslash, to keep the LaTeX strings below readable
PM = BS + ",$" + BS + "pm$" + BS + ","     # "\,$\pm$\,"
EOL = BS + BS                                # LaTeX row terminator
G = json.loads((HERE / "results_guard.json").read_text(encoding="utf-8")) if (HERE / "results_guard.json").exists() else None


def table(header, rows, cols):
    top = [BS + "begin{tabular}{" + cols + "}", BS + "toprule", header + EOL, BS + "midrule"]
    return "\n".join(top + rows + [BS + "bottomrule", BS + "end{tabular}"]) + "\n"


if G:
    def gm(name, var, f):
        return st.mean(g[name][var][f] for g in G) * 100

    def gms(name, var, f):
        v = [g[name][var][f] * 100 for g in G]
        return f"{st.mean(v):.1f}{PM}{st.stdev(v):.1f}"

    names = (("standard", "Standard guard (deployed)"), ("sentence_coverage_0.8", "Sentence coverage $" + BS + "geq 0.8$"),
             ("entity_span", "Entity-span guard (proposed)"))
    rows = [label + " & " + " & ".join(gms(n, "all", f) for f in ("correct", "wrong_entity", "false_answer_unanswerable")) + EOL for n, label in names]
    write("guard.tex", table("Guard & Correct (" + BS + "%) & Wrong entity (" + BS + "%) & False answers (" + BS + "%)", rows, "lrrr"))

    rows = []
    for var, label in (("keyword", "Keyword-aligned"), ("synonym", "Synonym")):
        for (n, _), short in zip(names, ("Standard", "Sent. cov. 0.8", "Entity-span")):
            rows.append(f"{label} & {short} & " + " & ".join(gms(n, var, f) for f in ("correct", "wrong_entity", "false_answer_unanswerable")) + EOL)
    write("guard_by_type.tex", table("Queries & Guard & Correct (" + BS + "%) & Wrong entity (" + BS + "%) & False answers (" + BS + "%)", rows, "llrrr"))

    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    for var, c, mk in (("keyword", "#1b9e77", "o"), ("synonym", "#7570b3", "s")):
        x = [st.mean(s["E3_strict_guard"][f"{t}|{var}"]["false_answer_unanswerable"] for s in S) * 100 for t in taus]
        y = [st.mean(s["E3_strict_guard"][f"{t}|{var}"]["correct"] for s in S) * 100 for t in taus]
        ax.plot(x, y, "-", marker=mk, ms=3, color=c, alpha=.8, label=f"Sentence coverage, {var}")
        ax.plot([gm("entity_span", var, "false_answer_unanswerable")], [gm("entity_span", var, "correct")], marker="*", ms=11, color=c, mec="k",
                ls="none", label=f"Entity-span, {var}")
    ax.set_xlabel("False answers on unanswerable questions (%)"); ax.set_ylabel("Correct answers (%)"); ax.legend(frameon=False, fontsize=6)
    fig.tight_layout(); fig.savefig(OUT_F / "guard_tradeoff.pdf"); plt.close(fig)

# ---------------- macros: every number quoted in the text
M = {}
pc = lambda x, d=1: f"{x:.{d}f}"
mean = lambda f: st.mean(f(s) for s in S)
thou = lambda n: f"{n:,}".replace(",", "{,}")
for typ, T_ in (("keyword", "Kw"), ("synonym", "Syn")):
    for mode, Md in (("lexical", "Bm"), ("dense", "Dn"), ("hybrid", "Hy")):
        M[f"R{T_}{Md}One"] = pc(mean(lambda s: s["E1_by_query_type"][mode][typ]["recall@1"]) * 100)
        M[f"R{T_}{Md}Five"] = pc(mean(lambda s: s["E1_by_query_type"][mode][typ]["recall@5"]) * 100)
        M[f"R{T_}{Md}Mrr"] = pc(mean(lambda s: s["E1_by_query_type"][mode][typ]["mrr"]), 3)
for mode, Md in (("lexical", "Bm"), ("dense", "Dn"), ("hybrid", "Hy")):
    M[f"ROverall{Md}"] = pc(mean(lambda s: s["E1_retrieval"][mode]["recall@1"]) * 100)
for key, Nm in (("no_acl", "NoAcl"), ("postfilter", "Post"), ("prefilter", "Pre")):
    M[f"Acc{Nm}"] = pc(mean(lambda s: s["E2_access"][key]["auth_correct"] / s["E2_access"][key]["auth_total"]) * 100)
    M[f"Leak{Nm}"] = pc(mean(lambda s: s["E2_access"][key]["unauth_leak"] / s["E2_access"][key]["unauth_total"]) * 100)
    M[f"TopFive{Nm}"] = pc(mean(lambda s: s["E2_access"][key]["unauth_hits_leak"] / s["E2_access"][key]["unauth_total"]) * 100)
    M[f"Abst{Nm}"] = pc(mean(lambda s: s["E2_access"][key]["unauth_abstain"] / s["E2_access"][key]["unauth_total"]) * 100)
for k, kn in (("1", "One"), ("2", "Two"), ("3", "Three"), ("10", "Ten")):
    for name, Nm in (("prefilter", "Pre"), ("postfilter", "Post")):
        M[f"K{kn}{Nm}"] = pc(mean(lambda s: s["E2_ksweep"][name][k]) * 100)
M["UnauthPairs"] = thou(S[0]["E2_access"]["prefilter"]["unauth_total"]); M["AuthPairs"] = thou(S[0]["E2_access"]["prefilter"]["auth_total"])
for f_, Fn in (("correct", "Corr"), ("wrong_entity", "Wrong"), ("abstain_answerable", "Abst"), ("false_answer_unanswerable", "False")):
    M[f"GStd{Fn}"] = pc(mean(lambda s: s["E3_guard"]["0.55"][f_]) * 100)
    for tau, Tn in (("0.8", "Eight"), ("0.9", "Nine")):
        M[f"GCov{Tn}{Fn}"] = pc(mean(lambda s: s["E3_strict_guard"][f"{tau}|all"][f_]) * 100)
M["GCovNineSynCorr"] = pc(mean(lambda s: s["E3_strict_guard"]["0.9|synonym"]["correct"]) * 100)
M["GCovEightSynCorr"] = pc(mean(lambda s: s["E3_strict_guard"]["0.8|synonym"]["correct"]) * 100)
if G:
    for name, Nn in (("standard", "S"), ("entity_span", "E")):
        for var, Vn in (("all", "All"), ("keyword", "Kw"), ("synonym", "Syn")):
            for f_, Fn in (("correct", "Corr"), ("wrong_entity", "Wrong"), ("false_answer_unanswerable", "False"), ("precision", "Prec"), ("abstain_answerable", "Abst")):
                M[f"G{Nn}{Vn}{Fn}"] = pc(gm(name, var, f_))
    for k_, Nn in (("standard", "S"), ("entity_span", "E")):
        M[f"Subst{Nn}"] = pc(st.mean(g["unauthorised_answered"][k_]["rate"] for g in G) * 100)
M["FaithLines"] = thou(sum(s["E4_faithfulness"]["answer_lines"] for s in S)); M["FaithVerbatim"] = thou(sum(s["E4_faithfulness"]["verbatim_lines"] for s in S))
a5, a1 = R["E7_audit"]["5000"], R["E7_audit"]["1000"]
M["AuditDetected"] = str(a5["detected"] + a1["detected"]); M["AuditTrials"] = str(a5["tamper_trials"] + a1["tamper_trials"])
M["AuditVerifyFive"] = pc(a5["verify_seconds"], 2)
if "E5_scaling" in R:
    for n, Nn in (("1000", "OneK"), ("5000", "FiveK"), ("20000", "TwentyK"), ("50000", "FiftyK")):
        for role, Rn in (("employee", "Emp"), ("admin", "Adm")):
            M[f"Lat{Nn}{Rn}PFifty"] = pc(R["E5_scaling"][n][role]["p50_ms"], 0); M[f"Lat{Nn}{Rn}PNinetyFive"] = pc(R["E5_scaling"][n][role]["p95_ms"], 0)
if FMT:
    M["FmtMinExtract"] = pc(min(v["extraction_rate"] for v in FMT.values()) * 100, 0)
    M["FmtMinThree"] = pc(min(v["recall_at_3"] for v in FMT.values()) * 100); M["FmtMaxThree"] = pc(max(v["recall_at_3"] for v in FMT.values()) * 100)
    M["FmtMinOne"] = pc(min(v["recall_at_1"] for v in FMT.values()) * 100); M["FmtMaxOne"] = pc(max(v["recall_at_1"] for v in FMT.values()) * 100)
if FMT:
    oth = [v for k, v in FMT.items() if k != "md"]
    M["FmtMdThree"] = pc(FMT["md"]["recall_at_3"] * 100); M["FmtOthMinThree"] = pc(min(v["recall_at_3"] for v in oth) * 100)
    M["FmtOthMaxThree"] = pc(max(v["recall_at_3"] for v in oth) * 100)
    M["FmtMdChunks"] = str(FMT["md"]["chunks"]); M["FmtOthChunks"] = str(round(st.mean(v["chunks"] for v in oth)))
M["NDocs"] = str(S[0]["docs"]); M["NFacts"] = str(S[0]["facts"]); M["NChunks"] = str(round(mean(lambda s: s["chunks"])))
M["NAnswerable"] = thou(S[0]["answerable"]); M["NUnanswerable"] = str(S[0]["unanswerable"]); M["NSeeds"] = str(len(S))
(OUT_T / "numbers.tex").write_text("\n".join(BS + "newcommand{" + BS + k + "}{" + v + "}" for k, v in M.items()) + "\n", encoding="utf-8")
