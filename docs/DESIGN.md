# triage-kit 设计文档

> 从 pier 评测框架解耦的独立评测结果归因 + 任务质检工具包（资产源自 Harbor 生态）
> 状态：方案设计稿（未实现） | 日期：2026-10-08（v2：纳入 check、修正血缘结论）

---

## 一、背景与目标

pier（Harbor fork）提供了一套 LLM 驱动的评测后处理能力（badcase 筛选 + 归因分析 + 任务质检），但存在两个束缚：

1. **LLM 后端硬绑定**：全包唯一 `claude_agent_sdk` import 点在 `src/pier/analyze/backend.py`，`-m` 只接受 Claude 模型，无法使用 GLM 等其他模型；
2. **与 pier 主框架耦合**：依赖 `pier.models.trial.result.TrialResult`（pydantic 校验）、`pier.cli.quality_checker` 的模型类。

**血缘查证结论（2026-10-08，经 Harbor 上游核实）**：`analyze` 与 `check` 均为从 Harbor **vendored**（原样搬运）的能力（对应 Harbor 原生 `harbor task debug` 与 `harbor task check`），其 prompt/rubric 资产是 Harbor 生态的公共资产。多步任务（steps/）与 Windows 支持（TaskOS/.bat）亦为 Harbor 原生格式，非 pier 发明；经查证 pier 在任务格式层唯一真实的新增是 `pre_artifacts.sh`。

因此 triage-kit 的解耦本质是**恢复这些资产的 Harbor-native 本来形态**（回归上游原始定位），而非移植改造。triage-kit 的目标：**将归因（analyze）与任务质检（check）能力解耦为独立可本地运行的工具包**，agent 粒度后端可插拔（general harness 挂任意 OpenAI-compatible LLM），原生兼容 Harbor 任务与评测结果，产物格式保持 pier/Harbor viewer 可读，覆盖"任务质量 → 评测 → 归因"完整链条。

**核心设计哲学继承自 pier 原版**：把"判定标准"从 prompt 里抽出来变成数据（rubric），让输出 schema 随 rubric 动态生成，实现无改码的评测维度扩展。

---

## 二、已收敛的核心决策

| 决策点 | 结论 |
|---|---|
| 运行形态 | 独立 CLI + TRAE skill 双形态，共享资产单源维护 |
| 后端架构 | agent 粒度契约 `query_agent -> (result, meta)`；general harness（自研循环挂任意 OpenAI-compatible）+ trae harness（宿主即循环）；claude SDK 保留为参照实现 |
| Harbor 兼容 | 朴素 JSON 读取替代 TrialResult，原生支持（已用真实样本验证字段布局，含 f2p/p2p/partial 细分维度透传） |
| check 融合 | **check（任务质检）纳入首批范围**，与 analyze 共享契约/编译管线/全部三个 harness，引擎零新增——仅增加 `task_reader` + `checker` 编排 + `triage check` 子命令 |
| 多步任务策略 | 检测到 `steps/` 时**逐 step 展开**检查（per-step 结果 + 汇总），修复 Harbor 上游继承的盲区（根目录 instruction/tests 为空时 criteria 失效），是 triage-kit 相对上游的第一个增值点 |
| check 文案 | check.txt 首句 "Pier task" 改回 "**a Harbor task**"——恢复上游原貌，保持与 Harbor 资产的可 diff 同步性 |
| check 产物 | 落盘 `<task_dir>/check-result.json`（与 task 同居便于归档）；analyze 产物路径不变 |
| 结构化输出 | general harness 用 final-tool 技巧（`submit_analysis` 强制调用，tool calling 参数校验兜底） |
| 安全与预算 | general harness 内置路径沙箱（cwd∪add_dirs 白名单）+ max_turns + 工具输出截断 |
| 日志 | 可选，general harness 内部，至少含完整工具调用序列 |
| 包形态 | 先内部模块，出现第二个消费者（critique 迁移等）再拆独立包 |
| analyze 产物契约 | `analysis.json/md` 格式与落盘路径不变，pier viewer 可读 |
| task 目录 | analyze 的降级路径按主路径设计（跨机器拷贝场景 task path 必然失效），支持 `--task-dir` 覆盖 |
| 项目名 | `triage-kit`（去 pier 化命名；NOTICE 保留 Harbor Apache 2.0 血缘致谢） |

---

## 三、架构：三层结构

```
Agent 契约（唯一的接口层）
  query_agent(prompt, cwd, tools, add_dirs, output_schema) -> (result, meta)
        │
        ├── general harness ── 自研工具循环，挂任意 OpenAI-compatible LLM
        │       （模型 = 参数，换 GLM/DeepSeek/Qwen/中转只改环境变量）
        │
        ├── trae harness ──── 循环由 TRAE 宿主提供，SKILL.md 是资产包
        │
        └── claude harness ── 参照实现：原 pier backend.py 移植，几乎原样
```

**关键分界线**：
- `core/` 只 import `contract.py` 定义的 Protocol，不知道任何后端存在
- `backends/` 各自实现契约，互不知晓
- `cli.py` 负责"选择哪个后端"的装配动作
- 归因的多轮探索（trajectory.json 可能几百 KB，judge 需选择性读取）决定了契约必须定在 **agent 粒度**而非模型粒度（单发 chat），否则工具循环会侵入编排层

**契约元数据（AgentMeta）**：字段可空但结构固定，下游按"有就用、没有就忽略"消费：

```python
class AgentMeta(BaseModel):
    n_turns: int                 # 工具循环轮数（max_turns 诊断依据）
    n_input_tokens: int | None   # None = 该 harness 不提供（如 trae）
    n_output_tokens: int | None
    cost_usd: float | None
    model: str                   # 实际使用的模型标识
```

---

## 四、目录全景

```
triage-kit/
│
├── assets/                          ← 【资产层】与代码完全解耦的纯文本，按工作流分目录收编
│   ├── analyze/                     归因工作流的资产
│   │   ├── analyze.txt              主归因 prompt 模板（占位符: {task_section} {criteria_guidance}）
│   │   ├── analyze-rubric.toml      默认归因判定标准（reward_hacking / task_specification）
│   │   └── analyze-job.txt          job 级聚合 prompt 模板（占位符: {trial_results}）
│   └── check/                        任务质检工作流的资产
│       ├── check.txt                 任务质检 prompt 模板（占位符: {file_tree} {criteria_guidance}；首句改回 "a Harbor task"）
│       └── rubrics/                  【rubric 家族机制】rubric 是纯数据，定制化扩展零架构成本
│           ├── check-default.toml    通用 11 条 criteria（Harbor vendored 原版基线，四组：双向完备性/防作弊/可复现性/工程卫生）
│           ├── check-deep-swe.toml   DeepSWE 家族定制版（只修 guidance 文本层，不动 criteria 结构，与 default 保持可对照）
│           ├── KNOWN-ISSUES.md       rubric 已知缺陷 backlog（见下文"rubric 质量优化机制"）
│           └── <family>.toml         未来其他数据集家族；CLI -r 指定或按目录特征自动探测
│
├── core/                            ← 【契约+编排层】零 LLM 依赖、零 pier 依赖
│   ├── contract.py                  AgentBackend Protocol + AgentMeta（契约唯一定义处）
│   ├── rubric.py                    inline 的 4 个 pydantic 类 + load_rubric（TOML/YAML/JSON）
│   ├── schema.py                    build_response_model / build_check_response_model（rubric → 动态输出模型，analyze/check 共用）
│   ├── trial_reader.py              Harbor/pier 朴素 JSON 读取（badcase 筛选 + task 目录定位 + 降级）
│   ├── task_reader.py               task 目录定位 + is_valid 等价校验 + 多步任务检测（steps/ 存在时逐 step 展开）
│   ├── analyzer.py                  analyze 编排：缓存→渲染→调 backend→校验→落盘→二级聚合
│   └── checker.py                   check 编排：file_tree 渲染→单次调用→校验→落盘 check-result.json；多步时逐 step
│
├── backends/                        ← 【实现层】契约的三个实现，互不知晓
│   ├── general/                     general harness（自研工具循环）
│   │   ├── harness.py              循环主体：messages 累积 → LLM → tool calls → 执行 → 循环
│   │   ├── tools.py                 read_file / glob / grep 三工具 + 路径沙箱
│   │   ├── structured.py            final-tool 技巧：submit_analysis schema 生成 + tool_choice 强制
│   │   └── debug_log.py             可选内部日志（工具调用序列 + token 用量）
│   ├── claude/                      参照实现：原 pier backend.py 去 pier import
│   └── trae/                        trae harness 的资产包（不是 Python）
│       └── SKILL.md                 触发条件 + 执行规程 + 输出契约 + 资产索引
│
├── cli.py                           入口：triage analyze / triage check
├── models_result.py                 AnalyzeResult / JobAnalyzeResult / CheckResult（产物模型）
└── pyproject.toml                   依赖仅: pydantic + typer + openai (+ claude_agent_sdk 可选)
```

---

## 五、触发方式

### 独立 CLI 形态

```bash
# 单 trial 归因（最常见：拿到一个可疑结果，查它）
triage analyze <trial_dir> --backend general --model glm-4.7

# job 级批量归因（筛 badcase + 并发 + 聚合）
triage analyze <job_dir> --failing --backend general --n-concurrent 5

# 自定义判定维度（rubric 可替换，schema 随之动态生成）
triage analyze <trial> --backend general --rubric my-rubric.toml

# Claude 参照实现（对照验证 general harness 归因质量）
triage analyze <trial> --backend claude -m sonnet

# 任务质量检查（评测前预检，排除任务缺陷导致的伪 badcase；产物落盘 <task_dir>/check-result.json）
triage check <task_dir>

# 家族定制 rubric（显式指定；或按目录特征自动探测，如 tests/ 含 grader.py+config.json 即 deep-swe 家族）
triage check <task_dir> -r deep-swe

# 多步任务自动逐 step 展开（per-step 结果 + 汇总）
triage check <multi_step_task_dir>

# 跨机器拷贝场景：手动覆盖 task 目录位置
triage analyze <trial> --task-dir /local/path/to/task
```

环境变量：
- `OPENAI_BASE_URL` + `OPENAI_API_KEY`（general harness，任意 OpenAI-compatible 端点）
- `ANTHROPIC_API_KEY`（claude 后端）

### TRAE skill 形态

无命令、无运行时——`backends/trae/SKILL.md` 放入 TRAE skills 目录后，对话中说"帮我归因这个 trial 目录 `…/ts-pattern-match-each__9giF4pL`，重点看是否作弊"即触发。TRAE agent 天然具备 Read/Glob/Grep，按 SKILL.md 规程读取同一份 assets/ 资产执行，产出同格式文件。

注：`--backend trae` 不作为 CLI 选项（trae harness 是 skill 形态，CLI 只有 `--backend general|claude`）。

---

## 六、执行结果：产物布局

对 job 目录跑完后（与 pier viewer 兼容）：

```
<job_dir>/                                       ← job 目录
├── analysis.json                               【新增】job 级聚合
├── analysis.md                                 【新增】job_summary 文本版
└── ts-pattern-match-each__9giF4pL/
    ├── result.json                             （原有，只读）
    ├── agent/trajectory.json                  （原有，只读——judge 的证据源）
    ├── analysis.json                           【新增】单 trial 归因
    └── analysis.md                            【新增】人读版
```

`analysis.json` 内容示例：

```json
{
  "trial_name": "ts-pattern-match-each__9giF4pL",
  "summary": "Agent 在 3 轮内定位到 matchEach 的类型收窄缺陷…通过了全部 91 个测试。",
  "checks": {
    "reward_hacking": {
      "outcome": "pass",
      "explanation": "trajectory 第 4-7 步显示 agent 修改了 src/ 下的实现文件，未触碰 tests/ 或 reward 文件，解决方式合法。"
    },
    "task_specification": {
      "outcome": "pass",
      "explanation": "instruction.md 中对 each 的返回结构有明确示例，测试断言与之对应，agent 失败属能力问题而非任务缺陷。"
    }
  }
}
```

- stdout 输出 meta 摘要（`n_turns / tokens / cost`）
- general harness 调试日志（可选开关）记录 judge 完整工具调用序列（可审计"judge 看了什么证据"）
- 缓存语义与 pier 原版一致：`analysis.json` 已存在则复用，`--overwrite` 强制重跑；job 级"全缓存且结果存在"则跳过聚合

**check 产物**（新增约定）：

```
<task_dir>/
├── check-result.json               【新增】11 条 criteria 判定结果
└── （多步任务时：steps/<step-n>/check-result.json + 顶层汇总）
```

`check-result.json` 内容示例：

```json
{
  "checks": {
    "behavior_in_task_description": {
      "outcome": "pass",
      "explanation": "instruction.md 明确描述了输出文件的 schema 与命名，测试断言均可溯源到 instruction。"
    },
    "pinned_dependencies": {
      "outcome": "fail",
      "explanation": "environment/Dockerfile 中 pip install requests 未 pin 版本。"
    }
  }
}
```

- check 与 analyze 的业务闭环：check 的 `behavior_in_task_description`（考了没写）是 analyze 的 `task_specification`（失败归因于任务缺陷）在**评测前**的镜像——上游拦住的缺陷正是下游归因时要剥离的噪声

---

## 七、数据流

**analyze（trial 侧归因）**：

```
用户触发 → trial_reader 朴素读 result.json（筛 badcase / 定位 task 目录，Harbor 原生兼容）
        → analyzer 渲染 prompt（assets 模板 + rubric 编译产物 guidance/schema）
        → backend（三选一）执行 agent 循环，返回 (result, meta)
        → schema 校验（失败提示换更强模型）→ analysis.json/md 落盘（viewer 可读）
        → job 级二级聚合（各 trial summary + checks 拼接，无工具纯 LLM 调用）
```

**check（task 侧质检）**：

```
用户触发 → task_reader 校验 task 目录（is_valid 等价物；steps/ 存在则逐 step 展开）
        → checker 渲染 prompt（file_tree + criteria_guidance 注入）
        → backend（三选一）执行 agent 循环，返回 (result, meta)
        → schema 校验 → check-result.json 落盘（多步：per-step + 汇总）
```

---

## 八、rubric 家族机制与质量优化机制

### 1. rubric 家族机制（数据驱动的定制化扩展）

rubric 本身是纯数据（TOML），因此针对特定数据集家族做定制 rubric 是**零架构成本**的一等扩展——不需要任何插件机制，`load_rubric` + `-r` 参数天然支持。

- **家族探测**：CLI `-r deep-swe` 显式指定；或按目录特征自动探测（如 tests/ 同时含 grader.py + config.json 即识别为 deep-swe 家族）
- **合并策略：先整体替换，后按需引入继承**。家族 rubric 先做成完整独立 TOML（结构重复可容忍，rubric 文件很小）；待出现第三个家族、重复维护成为真实痛点时，再给 `load_rubric` 加 `base` 继承合并（~20 行）——届时有两个真实家族样本可参照设计合并语义，优于现在凭空预设
- **deep-swe 家族版的原则**：只修 guidance 文本层（把已知误判指纹写死，如 "tests/Dockerfile COPY tests/ 是合法的独立验证环境模式"、"/opt 树外安装测试 reporter 是防作弊设计"），**不动 criteria 结构**——保持与 default 逐条可对照

### 2. KNOWN-ISSUES backlog（rubric 质量优化机制）

rubric 设计质量欠缺的问题**不在首期修**，而是预留文档化修改点，全流程打通后逐步优化：

- `assets/check/rubrics/KNOWN-ISSUES.md` 记录每条已知缺陷 + 证据案例（基于 2026-10-08 对 DeepSWE 113 个真实任务（ts-pattern-match-each 等）的逐条审读）：
  - **#4 tests_or_solution_in_image**：guidance 未覆盖双镜像分离模式（environment/Dockerfile 干净 + tests/Dockerfile 烤入测试是合法设计），有误判风险
  - **#5 test_deps_in_image**：guidance 把"镜像内测试工具"一律视为泄漏信号，未覆盖"树外安装（/opt）保持 /app 字节一致"的防作弊模式
  - **#7 pinned_dependencies**：guidance 以 Python 为中心（只写 pip 须 pin），未抽象为语言无关的"依赖安装必须可复现"原则
  - **#11 file_reference_mentioned**：严格度未按任务形态校准（SWE 任务惯例是 agent 自行探索入口文件，按数据产出型任务的标准会误判）
  - **#3 anti_cheating_measures**：存在性检查 ≠ 质量检查，对高工程化数据集无辨别力
- 优化节奏：**真实 badcase 驱动**——某次 check 误判 → 修对应 guidance → 在 KNOWN-ISSUES.md 记录案例闭环，不提前空想

### 3. 确定性前置层的位置（第二批工作）

check 对 DeepSWE 类任务最有价值的检查是**契约自洽性**（f2p/p2p node-id 与 test.patch 匹配、config.json 报告路径与 test.sh 产出路径一致、test.sh 防作弊声明与 solution.patch 触碰路径一致等）——这些是**确定性可验**的，不适合塞进 LLM rubric。规划位置：

- 作为家族的**伴生确定性脚本**（如 `core/contract_checks.py`），`triage check -r deep-swe` 时管线先跑确定性校验、结果注入 LLM 检查上下文（"以下契约已被程序验证/证伪"），LLM 只处理真正需要判断的部分
- 契合既有评测哲学：**确定性、低延迟的检查做 CI 门禁，LLM 判断做趋势分析**
- 时序：属于全流程打通后的第二批工作，首期只在架构上留出 checker.py 管线"前置层"的位置

---

## 九、实施步骤（按依赖顺序）

**第一批（打通全流程）**：

1. **抽取核心资产**：analyze 系列 3 份 + check 系列 2 份 prompt/rubric 复制（逐字节一致，仅 check.txt 首句 "Pier task"→"a Harbor task"；产物兼容的根基）+ inline 4 个 pydantic 类和 `load_rubric`（~100 行，零 pier 依赖）
2. **定义契约**：`contract.py`（AgentBackend Protocol + AgentMeta + `(result, meta)` 二元组）
3. **general harness**：工具循环 + 路径沙箱 + final-tool 结构化输出 + 预算约束（max_turns=15 起步、单文件读取截断）+ 可选调试日志
4. **trial_reader**：~30 行朴素 JSON 读取（筛选 + task 目录定位 + 降级 + `--task-dir` 覆盖）
5. **Analyzer 移植**：缓存/渲染/校验/落盘/二级聚合逻辑原样保留，去 pier import
6. **task_reader + Checker**：task 目录校验（is_valid 等价物）、file_tree 渲染、多步任务逐 step 展开、check-result.json 落盘
7. **CLI 入口**：typer 命令（`triage analyze` + `triage check`，含 `-r` rubric 选择与家族自动探测）+ 后端选择装配
8. **trae harness**：SKILL.md 包装同一套 assets（analyze 与 check 作为并列工作流）
9. **端到端验证**：对真实 Harbor job 的 trial 实跑 analyze；对 DeepSWE 数据集任务实跑 check（default 与 deep-swe rubric 各跑一遍，结果差异本身即 KNOWN-ISSUES 的实证）；claude/general 双后端对照归因；产物回灌 pier viewer 验证兼容

**第二批（全流程打通后）**：

10. **deep-swe 家族 rubric 编写**：按 KNOWN-ISSUES backlog 修 guidance 文本（#4/#5/#7/#11 四处指纹写死）
11. **确定性前置层**：`core/contract_checks.py`（config.json ↔ test.patch ↔ test.sh ↔ solution.patch 契约自洽校验），结果注入 LLM 上下文；可独立作为 CI 门禁使用
12. **rubric 继承机制**（条件触发）：出现第三个家族且重复维护成为痛点时，为 `load_rubric` 增加 `base` 继承合并

---

## 十、边界与已知取舍

- **失去 SDK 级 structured output 强约束**（general harness）：靠 final-tool 的 tool calling 参数校验兜底，格式漂移风险可控但非零
- **trae harness 无并发**：job 级批量在 TRAE 里只能串行或多次调用，不影响正确性
- **task 目录跨机失效是主路径**：样本验证发现 Linux 产出的 result.json 拷贝到 Windows 后 task path 必然不可解析，task_section 的降级话术（"infer from trajectory"）在跨机场景是常态而非边缘
- **多步任务逐 step 展开是 triage-kit 的增强**：Harbor/pier 的 check 原版对多步任务存在盲区（根目录 instruction/tests 为空时约 5 条 criteria 失去判定对象）——triage-kit 逐 step 展开修复此盲区，但意味着多步任务的 check 结果与 pier/Harbor 原版输出**不可直接对比**
- **check 文案与上游的可同步性**：check.txt 仅改首句（"Pier task"→"a Harbor task"），其余逐字节保留，将来 Harbor 上游 rubric/prompt 更新可 diff 同步
- **样本预判**：现有样本两个 trial 均 reward=1，`--failing` 筛出 0 个——首批实际用法是全量 analyze + 重点关注 `reward_hacking` check（"通过的 trial 也可能作弊"恰是这套 rubric 最独特的价值）
- **血缘法律留痕**：NOTICE 注明资产派生自 Harbor（Apache 2.0，vendored via pier），与 pier 的做法一致；assets 内容逐字节保留，命名层完全去 pier 化
- **rubric 质量的既知局限**：default rubric 为标准 Harbor 模板任务（harbor init 脚手架形态）设计，对高工程化数据集（如 DeepSWE）存在已知误判点（#3/#4/#5/#7/#11，详见 KNOWN-ISSUES backlog）——首期接受这些误判（check 首要目标是打通流程），家族 rubric + 确定性前置层在第二批逐步消化；check 的真实价值场景是**新任务入库门禁**，而非给成熟数据集复检（成熟数据集已有 tripwire/CI 同步等自有质量工程，边际价值低）
