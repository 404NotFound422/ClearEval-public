# 真实评估器实验记录框架 v2

本包提供来源服务器本地的 prepare、预算内 loopback 调用、外部真实调用导入与分析。候选、完整 teacher prompt、raw response 留在来源服务器；CLI 只显示数量和状态。当前本包实际模型请求为 0。10 个本地过程测试通过，使用合成传输；测试临时的八个 registry 条目不是八轮真实实验。

每个 study 最多准备八个不可覆盖的 round。manifest 冻结公开 candidate/source/requirements、实际 prompt 字节、teacher role/family/model/revision/声明参数、processor/renderer 源码及额外依赖。源码、prompt 或输入改变须另建 round。追加的 ledger 保留失败、重试、缓存来源与分母。每个候选/teacher 至少计划三次同配置独立调用；generation model 不充当跨家族 teacher 对照。

`--max-calls` 是整个 study 跨 round 累计的推理请求上限；新 round 不重置预算。默认禁止真实请求。提高上限仍须根代理明确授权。本次仅有两个既有固定 Q4 候选×三次同 prompt、temperature、seed，共六次 Qwen teacher 调用的预算；尚未上传或远端执行。

## 服务器接口

公共 case 为 `{id,task_id,input,input_sha256可选}`。input 至少含完整 protocol 与显式 requirements，或 requested_fields。单独 labels 文件不会被读取，label_key 等 envelope 元数据不进入 teacher。案例来源、任务 scope 迁移与来源版本须由 builder 明确记录；旧题候选不能据此获得新 253 题 scope 的效度。

`--builder module:function` 的函数签名为 `build_cases(candidate_dir: Path) -> list[case]`。它在服务器读取已经存在的候选/public_inputs/datasets。默认 renderer 将模板和 canonical public JSON 组成 prompt；`--prompt-builder module:function` 接 `render(public_input) -> str`，可在服务器调用新 scientific prompt builder。实际返回的完整 prompt 在服务器冻结。同一候选的不同 teacher 看到同一实际 prompt 字节。

纯离线 processor 签名为 `process(public_input, parsed_teacher_json) -> result`。有效状态可位于 `requirements` 或 `requirement_results`，每行有 id 和 effective_status/status。原始 proposed 可位于根 requirements 或 assessment.requirements。仅接受 SATISFIED / VIOLATED / UNDER_SPECIFIED / UNRESOLVED。processor 不能发送模型请求、读取私有标签或额外未共享材料；framework 冻结被调用模块，并可用重复 `--code-path <repo-relative.py>` 显式冻结其依赖。传入信息哈希相同不证明任意 Python callback 没有读取其他全局信息，仍须审核代码。

默认 core_guard 调用已有 contract.adjudicate；它是兼容的机械 guard，并不自动替代新 domain processor。processor 配置为 `[{"id":"grounded","entrypoint":"module:function"}]`。相同真实 raw/parsed 数据交给各 processor，比较记录 public input 与 parsed SHA。

本次 loopback teacher 配置需要明确 role=TEACHER、transport=OLLAMA_LOOPBACK、family、真实本地 model tag、完整 revision，以及 params：
`{"temperature":0,"seed":42,"num_ctx":8192,"num_predict":4096}`。实际 Qwen Q4 digest：
`25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`。
未知服务默认参数不补造；Ollama tags 在每次调用前后核验并保存，terminal done_reason 必须为 stop，返回 model 必须匹配。HTTP 仅允许 loopback，不用代理或 redirect，不读取私有 provider 配置。

示例仅为接口，不是执行记录：

```text
python -B -m experiments.evaluator_development_v2 prepare --study <server-study> --builder <module:build_cases> --candidate-dir <existing-qwen38_q4_r2> --judges <public-judges.json> --processors <public-processors.json> --prompt-builder <module:render_scientific_prompt> --code-path <processor-dependency.py> --label fixed-q4-r1 --repeats 3
python -B -m experiments.evaluator_development_v2 run-loopback --round <prepared-round> --max-calls 1 --allow-model-requests
python -B -m experiments.evaluator_development_v2 run-loopback --round <same-round> --max-calls 6 --allow-model-requests
python -B -m experiments.evaluator_development_v2 analyze --round <same-round>
```

成功 canary 是第一个 planned observation。失败后默认停下，后续 run 返回 FAILURE_REQUIRES_DIAGNOSIS；明确诊断后可用 acknowledge-failures 继续 pending，或另加 retry-failed 追加新 attempt，旧失败不删除。max-calls 包含已派发的失败请求。观察超时不代表进程终止；存活或未核清的 lock / STARTED attempt 会阻止重复派发，不自动删除。需要根代理确认原进程终止与 transport 状态后处理，不能仅因等待超时另起副本。

## Codex teacher 外部真实调用

不构造虚假的 GPT HTTP endpoint。EXTERNAL_ACTUAL teacher 的 revision 可为 UNKNOWN，params 可为 null，parameters_disclosure=UNAVAILABLE。每次真实独立调用的本地 response.json 为 `{"content":"原始模型JSON文字"}`；receipt 必须含 invocation_id、prompt_sha256、input_sha256、model、family、actual_revision、actual_params、cache_used=false、origin=EXTERNAL_ACTUAL。

```text
python -B -m experiments.evaluator_development_v2 import-external --round <round> --trial-id <planned-trial> --response <local-response.json> --receipt <local-call-receipt.json>
```

导入校验冻结输入及声明身份，拒绝复制 invocation 或把缓存当独立重复。receipt 是可审计的调用声明；它不认证 provider 隐藏上下文、私有参数或精确版本。不可获得的版本/参数必须保持 UNKNOWN/null，不能宣称严格模型版本稳定。不同 generation family 和旧 single-pass review 都不能冒充三次同 teacher prompt 的实验。

## 分析边界

计划 trial 是覆盖率分母，失败/缓存/fake 保留。统计 raw proposed 与实际 recomputed effective requirement 向量的 entropy、pairwise flip、decisive coverage，并分开 typed JSON 字段 exact-value entropy/flip。不同 teacher family 只有实际独立结果才进入跨家族摘要。三次调用只描述这组固定输入，不能当作三个独立科学题。全部 UNRESOLVED 的零 entropy 不算有效成功：decisive coverage 为 0、decisive entropy/risk 不可估计。

独立 labels 与 published parser/field correctness 评测是另一分析层。本包 repeat diagnostics 的 scientific_accuracy 与无参考 risk 始终为 null；真实发表事实抽取/ERR 标签只在后续明确预算与独立分析接口中使用，不把 literal/source consistency 等同湿实验质量。未运行正式 253 题、未宣称已完成专家一致性或 48 小时科学验证。

本机验证：

```text
python -B -m unittest experiments.evaluator_development_v2.test_runner -v
```

实际 10 PASS；失败留存/恢复、累计跨轮预算、八轮上限、prompt builder 字节、冻结输入、原始/parsed 缺失、terminal truncation、默认禁止真实请求、UNKNOWN coverage 与公开字段 SHA 均有过程检查。真实 Qwen 三重复证据尚不存在；已有五个 GPT6.1 single-pass 和变更提示的 r1/r2 不可复用为同输入稳定性。
