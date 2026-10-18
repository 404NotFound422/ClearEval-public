# 本地执行与故障续跑

## 本批能运行什么

本批可完整重建20组纯LF格式控制，验证原题原答绑定、逐行不变和可逆补丁，并执行24项工程测试。它不含完整评分runner，不能执行新的V4/V5科学评分。后续runner应有独立版本、依赖和真实执行记录，不能把本批工程PASS当作科学验收。

## 安装与准备

1. 检出本仓库的 `research/supplement-validation-20261018` 分支，保留仓库中的 `dataset/Q+AR/model_response/` 数据文件。
2. 使用Python 3.10或更新版本。已在Python 3.12.14实测。此批只依赖Python标准库，不需要pip安装、账号、API密钥、模型权重、GPU或云服务。
3. 进入 `research/supplement-validation-20261018/` 目录。三个依赖源文件必须与manifest固定的SHA256/Git blob一致；无需把Git HEAD回退到旧提交。

Linux/macOS：

```sh
python3 --version
python3 -B scripts/reproduce.py
```

Windows PowerShell（使用已安装的Python）：

```powershell
python --version
python -B scripts/reproduce.py
```

如果本目录被单独复制到别处，可显式指定包含公开数据的本地仓库根目录：

```sh
python3 -B scripts/reproduce.py --repo-root ../../ClearEval-public
```

整个命令只读源数据、写本目录下的 `build/`；不会联网、启动GitHub Actions、调用模型或编码器，也不要求任何外部许可记录。

## 结果保存位置

- `build/inputs/candidate20_original_pairs.json`：从固定公开源文件提取的20条原题原答。`source_path`为仓库相对路径。
- `build/format_controls/format_control_pairs.json`：20组原始/变体完整对应记录。
- `build/format_controls/pairs/` 和 `diffs/`：逐组记录、原行映射、插入位置及可逆补丁。
- `build/format_controls/validation_summary.json`：构造检查与边界声明。
- `build/reproduced_format_metrics.json`：每组原答、变体和diff哈希；必须与已发布基线完全一致。
- `build/test_results.txt`：18项格式回归＋6项输入完整性测试的实际日志。
- `build/reproduction_result.json`：最终机器可读结果。成功时 `published_metrics_exact_match=true`、`test_process_exit_code=0`。

正常结果为20/20格式对通过、814原行逐字不变、插入172个LF、986变体行，0 encoder、0 judge、0科学评分运行。生成内容仅用于对被评价文本的格式控制，不构成实验操作建议。

`build/` 已被本目录的 `.gitignore` 排除。保存失败材料或自己的后续科学结果时，应先做独立目录和版本标识；不要直接把其内容批量公开。

## 只读复核

```sh
python3 -B scripts/build_format_controls.py --verify
```

该命令不重建、不修改产物。如果源名单、内容、逐组文件、行映射、补丁或统计声明被改动，应失败，不能通过改掉校验值掩盖差异。

## 失败与续跑

- **源文件不存在或hash不符**：确认本地路径指向完整仓库，且三个源文件与 `metadata/candidate20_manifest.json` 指定提交内容一致。不要替换题干、答案或manifest哈希来强行通过。确需新样本时，应另建候选版本并重新核验。
- **构建中断、陈旧文件或额外文件导致失败**：先把当前 `build/` 改名保留为独立失败目录，再运行完整 `reproduce.py`。纯格式构造无付费或随机调用，完整重建是安全的续跑方式。
- **测试失败**：保留 `build/test_results.txt`；不得把非零退出码当作完成。检查Python版本和源文件后重新执行。不要把旧日志复制为新运行日志。
- **需要新科学分数**：本批尚不具备该能力。不得将空值填零、以纯格式测试代替科学判断，或把历史报告中的表格逆造成模型raw。完整runner与可用证据绑定应在后续版本另行核验。

本批没有内部批准锁。它的失败即停止规则只用于来源、格式与状态真实性验证。
