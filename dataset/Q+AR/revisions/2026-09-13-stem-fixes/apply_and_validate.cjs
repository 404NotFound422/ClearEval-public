// Apply the reviewed stem edits and verify the resulting dataset without model calls.
// Run from any working directory: node apply_and_validate.cjs
// Verify only after applying: node apply_and_validate.cjs --check
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const assert = require("node:assert/strict");

const revisionDir = __dirname;
const srcDir = path.resolve(revisionDir, "../../src");
const questionPath = path.join(srcDir, "question_final.json");
const restrictionPath = path.join(srcDir, "restrict.py");
const plan = JSON.parse(fs.readFileSync(path.join(revisionDir, "updates.json"), "utf8"));
const sha256 = value => crypto.createHash("sha256").update(value).digest("hex").toUpperCase();
const beforeDir = path.join(revisionDir, "before");
const checkOnly = process.argv.includes("--check");
const readJSON = file => JSON.parse(fs.readFileSync(file, "utf8"));
const writeJSON = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n", "utf8");

function baseline(file, expectedHash) {
  const backupPath = path.join(beforeDir, path.basename(file));
  if (fs.existsSync(backupPath)) {
    const original = fs.readFileSync(backupPath);
    assert.equal(sha256(original), expectedHash, "Baseline hash mismatch: " + backupPath);
    return original;
  }
  assert(!checkOnly, "Apply first to create the preserved baseline.");
  const original = fs.readFileSync(file);
  assert.equal(sha256(original), expectedHash, "Source changed since review: " + file);
  fs.mkdirSync(beforeDir, { recursive: true });
  fs.writeFileSync(backupPath, original, { flag: "wx" });
  return original;
}

const originalQuestionBytes = baseline(questionPath, plan.base_question_sha256);
const originalRestrictionBytes = baseline(restrictionPath, plan.base_restrict_sha256);
const originalQuestions = JSON.parse(originalQuestionBytes.toString("utf8"));
const originalRestrictions = originalRestrictionBytes.toString("utf8");
const updates = new Map(plan.updates.map(u => [u.question_id, u]));
assert.equal(updates.size, 253, "Expected one update per question.");
const expectedQuestions = originalQuestions.map(q => {
  const u = updates.get(q.question_id);
  assert(u, "Missing update for " + q.question_id);
  return {
    ...q,
    question: u.question,
    ...(u.marker_query_targets ? { marker_query_targets: u.marker_query_targets } : {})
  };
});
const originalEol = originalQuestionBytes.includes(Buffer.from("\r\n")) ? "\r\n" : "\n";
const expectedQuestionText = (JSON.stringify(expectedQuestions, null, 2) + "\n").replace(/\n/g, originalEol);
const markerMatch = originalRestrictions.match(/("Marker":\s*\{")([^"]+)("\})/);
assert(markerMatch, "Unexpected restrictions format.");
const markers = markerMatch[2].split("、").filter(m => m !== "Cx40 / Hcn4");
for (const marker of plan.added_markers) if (!markers.includes(marker)) markers.push(marker);
const expectedRestrictions = originalRestrictions.replace(
  markerMatch[0], markerMatch[1] + markers.join("、") + markerMatch[3]
);
const actual = checkOnly ? readJSON(questionPath) : expectedQuestions;
const restrictions = checkOnly ? fs.readFileSync(restrictionPath, "utf8") : expectedRestrictions;
assert.deepEqual(actual, expectedQuestions, "Dataset differs from reviewed update plan.");
assert.equal(restrictions, expectedRestrictions, "Restrictions differ from update plan.");
assert.equal(actual.length, 253);
assert.deepEqual(actual.map(q => q.question_id), originalQuestions.map(q => q.question_id));
assert.equal(new Set(actual.map(q => q.question)).size, actual.length, "Duplicate stems remain.");
assert.equal(plan.findings.length, 38);
const byId = new Map(actual.map(q => [q.question_id, q]));
const checks = [];
function check(name, fn) { fn(); checks.push(name); }
function everyQuestion(ids, predicate, message) {
  for (const id of ids) assert(predicate(byId.get(id)), message + " (question " + id + ")");
}
check("All 253 questions retain identifiers, order, and non-editorial metadata", () => {
  actual.forEach((q, i) => {
    assert.deepEqual(Object.keys(q), Object.keys(originalQuestions[i]));
    for (const key of Object.keys(q)) {
      if (!["question", "marker_query_targets"].includes(key)) {
        assert.deepEqual(q[key], originalQuestions[i][key]);
      }
    }
    assert(q.question.trim());
    assert(!/\uFFFD|TODO|待填写|待补充/.test(q.question));
    assert.equal((q.question.match(/请仅输出/g) || []).length, 1);
    assert(q.question.includes("必要的标记前处理、探针/抗体孵育与洗涤"));
    assert(q.question.includes("已明确完成且质控合格的标记步骤无需重复"));
  });
});
check("All review groups have coverage and valid question references", () => {
  for (const f of plan.findings) {
    assert.equal(f.status, "addressed");
    for (const id of f.qids) {
      assert(byId.has(id));
      assert(updates.get(id).issue_ids.includes(f.id));
      assert.notEqual(byId.get(id).question, originalQuestions.find(q => q.question_id === id).question);
    }
  }
});
check("Method identities and known invented reagent names corrected", () => {
  everyQuestion([12], q => !q.question.includes("100% 甲醇进入叔丁醇"), "Mixed solvent sequence");
  everyQuestion([48,52,56,100,112], q => q.question.includes("PEGASOS") && !/BoneClear|methanol/.test(q.question), "PEGASOS method identity");
  everyQuestion([72,76], q => !/FOCM-L|FOCM-R|使用 FOCM/.test(q.question), "FOCM mismatch");
  everyQuestion([84,216], q => !/gradient delipidation|主要适合较小样本/.test(q.question), "Ce3D mismatch");
  everyQuestion([128], q => !q.question.includes("EyeCi"), "EyeCi/CUBIC mismatch");
  everyQuestion([228], q => !q.question.includes("BoneClear-R") && q.question.includes("DBE"), "Undefined RI reagent");
  everyQuestion([232], q => !q.question.includes("uDISCO") && q.question.includes("FDISCO"), "THF method identity");
});
check("Internal thickness contradiction and duplicated scenario removed", () => {
  assert(!byId.get(32).question.includes("300 μm"));
  assert(byId.get(32).question.includes("500 μm"));
  assert.notEqual(byId.get(27).question, byId.get(28).question);
});
check("Perfusion timing and mouse placental circulation explicit", () => {
  everyQuestion([66,67,68,185,186,187,188,244], q => q.question.includes("固定前") && q.question.includes("在体血管腔面标记"), "Missing in vivo condition");
  everyQuestion([113,114,115,116,201,202,203,204], q => q.question.includes("E18.5") && q.question.includes("胎儿侧循环") && q.question.includes("迷路层") && !q.question.includes("绒毛"), "Placental anatomy/circulation");
});
check("DiI/DiD tasks state direct/local interpretation and label preservation", () => {
  everyQuestion([165,166,167,168], q => q.question.includes("不跨突触") && q.question.includes("膜内扩散已完成"), "Multisynaptic tracing");
  everyQuestion([221,222,223,224], q => q.question.includes("不作为跨突触") && q.question.includes("不恢复已切断"), "Disconnected visual tracing");
  assert(!byId.get(168).question.includes("充分脱水/脱脂"));
  assert(byId.get(168).question.includes("同类新固定样本"));
});
check("Reporter and sympathetic target metadata agree with stems", () => {
  const names = id => byId.get(id).marker_query_targets.map(m => m.marker_name);
  for (const id of [9,10,11,12,21,22,23,24,29,30,31,32]) assert(names(id).includes("EGFP"));
  for (const id of [61,62,63,64]) assert(names(id).includes("mCherry") && !names(id).includes("GFP (内源)"));
  for (const id of [189,190,191,192,248]) assert(names(id).includes("tdTomato") && !names(id).includes("GFP (内源)"));
  for (const id of [109,110,111,112,182,184]) assert(names(id).includes("TH"));
  actual.forEach(q => q.marker_query_targets.forEach((m, i) => {
    if (m.marker_slot === "question_specific") {
      assert.equal(m.source_tissue_xlsx_row, null, "New target must not claim an old worksheet row.");
      assert.equal(m.target_index, i + 1);
      assert.equal(m.query_path, [m.major_category, m.subcategory, m.structure_or_cell_subtype].join(" > "));
    }
  }));
  for (const id of [109,110,111,112]) assert(!JSON.stringify(byId.get(id).marker_query_targets).includes("感觉神经纤维"));
  for (const id of [113,114,115,116,201,202,203,204]) assert(!JSON.stringify(byId.get(id).marker_query_targets).includes("绒毛"));
  for (const id of [181,182,183,184]) assert(!JSON.stringify(byId.get(id).marker_query_targets).includes("胃壁"));
});
check("Required missing markers and explicit aliases available", () => {
  for (const marker of plan.added_markers) assert(markers.includes(marker), "Missing marker " + marker);
  assert(!markers.includes("Cx40 / Hcn4"), "Distinct targets still conflated.");
  assert(markers.includes("Cx40") && markers.includes("HCN4"));
});
check("All linked target names are covered by markers, aliases, or allowed direct labels", () => {
  const fluorMatch = restrictions.match(/"Dye_or_Fluorophore":\s*\{"([^"]+)"\}/);
  assert(fluorMatch);
  const normalize = name => name.toLowerCase().replace(/[^a-z0-9α-ω]/g, "");
  function parts(name) {
    const text = name.replace(/Hu\s*C\/D/gi, "HuCD").replace(/\breporter\b/gi, "");
    const aliases = [...text.matchAll(/\(([^)]+)\)/g)].map(m => m[1]);
    return [text.replace(/\([^)]*\)/g, ""), ...aliases]
      .flatMap(s => s.split(/[\/;]/)).map(s => s.trim()).filter(Boolean);
  }
  const allowed = new Set([...markers, ...fluorMatch[1].split("、")].flatMap(parts).map(normalize).filter(Boolean));
  for (const q of actual) for (const target of q.marker_query_targets) {
    for (const name of parts(target.marker_name)) {
      // Wnt1-Cre is the reporter's genetic context, not an extra staining target.
      if (name === "Wnt1-Cre") continue;
      const normalized = normalize(name);
      if (normalized) assert(allowed.has(normalized), "Unlisted linked target: " + q.question_id + " / " + name);
    }
  }
});
check("Prompt suffix permits repair of labeling, and new-sample scope is explicit", () => {
  everyQuestion([16,27,28,36,80,156,164,168,176,180,228], q => q.question.includes("探针/抗体孵育与洗涤"), "Labeling prohibited");
  for (const q of actual.filter(q => q.question.includes("修正后的 protocol"))) {
    assert(q.question.includes("修正版用于同类新样本"));
  }
  assert(!byId.get(140).question.includes("修正版"));
  assert(!byId.get(208).question.includes("修正版"));
});
check("Archived inputs match the pre-edit hashes", () => {
  assert.equal(sha256(fs.readFileSync(path.join(beforeDir, "question_final.json"))), plan.base_question_sha256);
  assert.equal(sha256(fs.readFileSync(path.join(beforeDir, "restrict.py"))), plan.base_restrict_sha256);
});

if (!checkOnly) {
  // All semantic checks pass before either live source is updated.
  for (const [file, beforeHash, afterText] of [
    [questionPath, plan.base_question_sha256, expectedQuestionText],
    [restrictionPath, plan.base_restrict_sha256, expectedRestrictions]
  ]) {
    const current = fs.readFileSync(file);
    assert(sha256(current) === beforeHash || current.equals(Buffer.from(afterText)),
      "Refusing to overwrite unrelated changes: " + file);
  }
  fs.writeFileSync(questionPath, expectedQuestionText, "utf8");
  fs.writeFileSync(restrictionPath, expectedRestrictions, "utf8");
  assert.deepEqual(readJSON(questionPath), expectedQuestions);
  assert.equal(fs.readFileSync(restrictionPath, "utf8"), expectedRestrictions);
}
const changedTargets = plan.updates.filter(u => u.marker_query_targets).map(u => u.question_id);
const substantiveIds = plan.updates.filter(u => u.changes.some(c => !/^G0[12]：|^关联目标复核：/.test(c))).map(u => u.question_id);
const manifest = {
  revision: plan.revision,
  question_count: actual.length,
  stem_updates: plan.updates.length,
  substantive_or_context_stem_updates: substantiveIds.length,
  output_scope_only_updates: actual.length - substantiveIds.length,
  marker_target_updates: changedTargets.length,
  added_marker_entries: plan.added_markers.length,
  addressed_review_groups: plan.findings.length,
  duplicate_stems: 0,
  question_ids_preserved: true,
  unrelated_question_fields_preserved: true,
  baseline_question_sha256: plan.base_question_sha256,
  current_question_sha256: sha256(fs.readFileSync(questionPath)),
  baseline_restrict_sha256: plan.base_restrict_sha256,
  current_restrict_sha256: sha256(fs.readFileSync(restrictionPath)),
  model_answers_and_scores_modified: false,
  checks_passed: checks,
  limitations: [
    "Checks validate data consistency and selected scientific constraints; they are not wet-lab validation.",
    "Historical model responses, scores, and derived preference vectors have not been recomputed for the revised stems.",
    "Added scenario conditions are benchmark inputs, not claims about actual experimental records."
  ]
};
writeJSON(path.join(revisionDir, "manifest.json"), manifest);
function csvCell(value) { return '"' + String(value ?? "").replace(/"/g, '""') + '"'; }
const csvRows = [["question_id","issue_ids","changes","before","after","markers_before","markers_after"]];
for (const q of actual) {
  const old = originalQuestions.find(o => o.question_id === q.question_id);
  const u = updates.get(q.question_id);
  csvRows.push([
    q.question_id, u.issue_ids.join("; "), u.changes.join("\n"), old.question, q.question,
    old.marker_query_targets.map(m => m.marker_name).join("; "),
    q.marker_query_targets.map(m => m.marker_name).join("; ")
  ]);
}
fs.writeFileSync(path.join(revisionDir, "changes.csv"), "\uFEFF" + csvRows.map(r => r.map(csvCell).join(",")).join("\r\n") + "\r\n", "utf8");
const readme = [
  "# 2026-09-13 题干修订", "",
  "已按用户授权修复题干及必要配套配置。保留全部 253 个题号及顺序，38 组审阅意见已处理。", "",
  "全部题干统一允许必要的标记前处理、孵育和洗涤；其中 " + substantiveIds.length + " 题另有科学条件、目标范围或措辞修订，" + changedTargets.length + " 题更新关联标记及分类路径。原始题库及白名单保存在 before/，历史模型回答和评分未改动。", "",
  "## 文件", "",
  "- [修改前后对照表](changes.csv)：全部253题原文、修订后文本、原因和关联标记。",
  "- [修订计划及文献](updates.json)：逐题更新、38组问题对应关系与原文献获取范围。",
  "- [验证记录](manifest.json)：前后哈希、统计和检查结果。",
  "- [修订前题库](before/question_final.json)与[修订前白名单](before/restrict.py)。", "",
  "## 主要处理", "",
  "- 方法归属：修复第12、48、52、56、72、76、84、100、112、128、216、228、232题的方法/试剂描述。第72题改为真实 CUBIC-L/CUBIC-RA 试剂的合成短流程排错情境。",
  "- 科学前提：补充既有报告和在体探针状态，区分小鼠胎盘迷路层的胎儿毛细血管与母体血窦；DiI/DiD 题改为直接投射段或分离组织内的局部判读。",
  "- 测量边界：区分神经结构与轴突再生、上皮身份与恶性判定、蛋白分布与超微结构/功能推断。",
  "- 数据一致性：第28题改为独立的高背景排错场景，第32题统一为500 μm；纠正报告蛋白、交感神经和辅助通道的关联标记。",
  "- 白名单：补齐审阅发现的必要靶点，并补齐 AMACR、PNAd、CD45、CD11b、CGRP 等原有关联目标；明确别名，分开 Cx40 与 HCN4。",
  "- 新增或替换的关联目标使用 marker_slot=question_specific、source_tissue_xlsx_row=null，避免声称来自未同步的原始工作表行。", "",
  "## 使用范围", "",
  "排错题为合成基准情境。新增采样时间、报告/示踪条件及处理记录属于修订后题目的明确输入，不能当作真实实验记录或已经验证的最优流程。原始文献获取限制保留在 updates.json 的 sources 中。", "",
  "原题号保持不变，但题干和全局白名单版本已经变化。历史回答和评分仍对应修订前输入，不能当作修订后成绩；旧运行按题号续跑时会命中历史文件。进行新实验时应使用独立输出目录，并重新生成回答及所需衍生数据。", "",
  "从任何目录运行 node apply_and_validate.cjs 应用修订；运行 node apply_and_validate.cjs --check 核对已修订文件。脚本拒绝覆盖与修订前快照或本次预期结果均不一致的源文件。", "",
  "## 审阅意见落实", "",
  "| 编号 | 题号 | 处理项 |", "|---|---|---|"
];
for (const f of plan.findings) readme.push("| " + f.id + " | " + f.qids.join(", ") + " | " + f.title + " |");
fs.writeFileSync(path.join(revisionDir, "README.md"), readme.join("\n") + "\n", "utf8");
console.log(JSON.stringify(manifest, null, 2));
