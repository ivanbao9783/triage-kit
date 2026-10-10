# triage-kit 设计文档

> 从 Harbor 生态评测工具链解耦的独立评测结果归因 + 任务质检工具包（资产源自 Harbor 生态）
> 状态：**as-built 架构快照（已实现）** | v4：2026-10-10（P012 后端收敛为 claude 单后端后重构；v3 为双后端快照，已废止）

---

## 一、文档定位与项目现状

本文档是**现状快照**：只描述已落地的架构与机制，不含实施计划——未来工作统一由 [ROADMAP.md](../ROADMAP.md) 跟踪（每个特性一份 `docs/proposals/` 设计文档，见 P000 流程）。文中所有命令、文件、函数名均对照代码核验过。

**项目现状**：CLI 三命令（analyze / check / clean）可用，137 项测试全绿，真实 LLM 端点（DeepSeek Anthropic 兼容端点）E2E 验证通过（含 113-trial 真实 job 的 badcase 回收），产物布局经真实样本实测。后端收敛为 **Claude Agent SDK 单后端**（P012）：自研 general harness 已整体退役。

---

## 二、背景与目标

上游评测框架（Harbor fork）提供了一套 LLM 驱动的评测后处理能力（badcase 筛选 + 归因分析 + 任务质检），但存在两个束缚：

1. **LLM 后端硬绑定**：唯一 `claude_agent_sdk` import 点，`-m` 只接受 Claude 模型；
2. **与上游主框架耦合**：依赖 `TrialResult`（pydantic 校验）等上游模型类。

**血缘查证结论（2026-10-08，经 Harbor 上游核实）**：`analyze` 与 `check` 均为从 Harbor **vendored**（原样搬运）的能力（对应 Harbor 原生 `harbor task debug` 与 `harbor task check`），prompt/rubric 资产是 Harbor 生态的公共资产。因此 triage-kit 的解耦本质是**恢复这些资产的 Harbor-native 本来形态**（回归上游原始定位），而非移植改造。

**目标**：将归因（analyze）与任务质检（check）能力解耦为独立可本地运行的工具包，agent 粒度后端可插拔（当前 Claude Agent SDK 单后端，通达 Anthropic 官方与 Anthropic 兼容端点如 DeepSeek；codex SDK / DeepSeek harness SDK 为规划中的后端），原生兼容 Harbor 任务与评测结果，产物格式保持稳定（未来 triage-kit 自建 viewer 按此读取），覆盖"任务质量 → 评测 → 归因 → 复原"完整链条。**项目核心价值在诊断 rubric 与 prompt 资产**——harness 管道交给专业 SDK 维护（P012 决策）。

**核心设计哲学继承自上游原版**：把"判定标准"从 prompt 里抽出来变成数据（rubric），让输出 schema 随 rubric 动态生成，实现无改码的评测维度扩展。

---

## 三、核心决策记录（ADR 摘要）

| 决策点 | 结论 | 状态 |
|---|---|---|
| 运行形态 | 独立 CLI + TRAE skill 双形态，共享资产单源维护 | CLI 已落地；skill 为 P001 |
| 后端架构 | agent 粒度契约 `query_agent -> (result, meta)`；**claude harness 单后端**（Claude Agent SDK，原上游 backend.py 移植；工具循环/上下文/结构化输出全由 SDK 承担）；trae harness 规划为 skill 形态，**不作为 CLI 选项**；codex / DeepSeek harness SDK 为规划后端（P012） | 已落地 |
| Harbor 兼容 | 朴素 JSON 读取替代 TrialResult，原生支持（真实样本验证过字段布局，含 f2p/p2p/partial 细分透传） | 已落地 |
| check 融合 | check 与 analyze 共享契约/schema 管线/两个 harness，引擎零新增——仅 `task_reader` + `checker` 编排 + `triage check` 子命令 | 已落地 |
| check 文案 | check.txt 仅改首句的项目名（改为 "**a Harbor task**"）——恢复上游原貌，保持与 Harbor 资产可 diff 同步 | 已落地 |
| 产物布局 | 全部落 `<dir>/triage-kit/` 子目录（analyze 与 check 同规则）：被评测目录零污染，`triage clean` 一条命令复原；不绑定任何上游 viewer 的落盘契约（用户决策 2026-10-09：当前无 viewer，未来自建，可自由采用新布局） | 已落地 |
| 结构化输出 | claude harness 经 SDK 的 `output_format: json_schema` 机制（schema 由 rubric 动态编译注入）——SDK 原生强约束，无格式漂移风险 | 已落地 |
| 安全与预算 | judge 禁读：check 侧 file_tree 排除 `triage-kit/`；analyze 侧 claude 路径的 CLI 工具缺口立项待办（P013）。上下文管理与轮次预算由 SDK CLI 承担 | check 侧已落地；P013 待办 |
| 缓存身份 | sidecar（`.meta.json`）记录 rubric 内容 sha256 + model；身份匹配复用、不匹配报错提示 `--force`、无 sidecar 的 legacy 产物视为 miss | 已落地 |
| 多语言 | `--lang zh`：`analysis.md` 由中文原生撰写二跳直接生成（输入为结构化 payload 而非英文 markdown，P009 路线 B）；`analysis.json` 恒英文；`analysis.zh.md` 退役 | 已落地 |
| 运行日志 | 每次 CLI 运行把执行日志落盘 `<CLI 参数目录>/triage-kit/run.log`（覆盖式、文件恒 DEBUG、控制台行为不变，P011）；与产物同生共死，`clean` 一并复原 | 已落地 |
| 复原 | `triage clean`：默认 dry-run，`--yes` 才删除；只删名为 `triage-kit/` 的目录，原生数据结构上不可能被误伤 | 已落地 |
| 多步任务 | **检测/校验已实现**（`task_reader.detect_steps` + validate 拒绝空 steps/）；**逐 step 展开检查未实现**（`checker` 为单次整体检查）——待立项 | 部分实现 |
| task 目录 | analyze 的降级路径按主路径设计（跨机器拷贝场景 task path 必然失效），支持 `--task-dir` 覆盖 | 已落地 |
| 项目名 | `triage-kit`（独立命名；NOTICE 保留 Harbor Apache 2.0 血缘致谢） | 已落地 |

---

## 四、架构：契约 + 单实现（多后端可插拔）

```
Agent 契约（唯一的接口层）
  query_agent(prompt, cwd, tools, add_dirs, output_schema) -> (result, meta)
        │
        ├── claude harness ── 主实现：Claude Agent SDK（原上游 backend.py 移植）
        │       工具循环/上下文管理/结构化输出全由 SDK 内置 CLI 承担；
        │       端点 = ANTHROPIC_BASE_URL（Anthropic 官方 / DeepSeek 等
        │       Anthropic 兼容端点），模型 = 参数（-m）
        │
        ├── trae harness ──── 规划形态：循环由 TRAE 宿主提供，SKILL.md 是资产包（P001）
        │
        ├── codex harness ─── 规划（用户已排期意向，未立项）
        └── deepseek harness ── 规划（DeepSeek 原生 SDK，未立项）
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
    n_input_tokens: int | None   # None = 该 harness 不提供
    n_output_tokens: int | None
    cost_usd: float | None
    model: str                   # 实际使用的模型标识
```

---

## 五、目录全景（真实文件树）

```
triage-kit/
│
├── assets/                          ← 【资产层】纯文本，按工作流分目录
│   ├── analyze/
│   │   ├── analyze.txt              主归因 prompt 模板（占位符: {task_section} {criteria_guidance}）
│   │   ├── analyze-rubric.toml      默认归因判定标准（reward_hacking / task_specification）
│   │   └── analyze-job.txt          job 级聚合 prompt 模板（占位符: {trial_results}）
│   └── check/
│       ├── check.txt                任务质检 prompt 模板（占位符: {file_tree} {criteria_guidance}）
│       └── rubrics/
│           ├── check-default.toml   通用 11 条 criteria（Harbor vendored 原版基线）
│           └── KNOWN-ISSUES.md      rubric 已知缺陷 backlog（见第八节）
│
├── src/triage_kit/
│   ├── core/                        ← 【契约+编排层】零 LLM 依赖、零上游框架依赖
│   │   ├── contract.py              AgentBackend Protocol + AgentMeta（契约唯一定义处）
│   │   ├── rubric.py                rubric pydantic 类 + load_rubric（TOML）
│   │   ├── schema.py                build_analyze_response_schema / build_check_response_schema /
│   │   │                            to_json_schema_dict（rubric → 动态输出模型，analyze/check 共用）
│   │   ├── trial_reader.py          Harbor 布局朴素 JSON 读取（badcase 筛选 + trial 目录判定）
│   │   ├── task_reader.py           task 目录校验（is_valid 等价物 + steps/ 多步检测）+ file_tree 渲染
│   │   ├── cache.py                 缓存三态：resolve_cache（身份比对）+ write_json（产物+sidecar）
│   │   ├── analyzer.py              analyze 编排：缓存→渲染→调 backend→校验→落盘→job 级聚合→翻译二跳
│   │   └── checker.py               check 编排：file_tree 渲染（排除 triage-kit/）→单次调用→校验→落盘
│   │
│   ├── backends/                    ← 【实现层】
│   │   ├── claude/
│   │   │   └── harness.py           主实现：原上游 backend.py 去框架 import（Read/Glob/Grep + output_format via Agent SDK）
│   │   └── trae/                    占位（`__init__.py`）；SKILL.md 资产包为 P001
│   │
│   └── cli.py                       入口：triage analyze / check / clean
│
├── tests/                           ← pytest，137 项；conftest.py 集中共享工厂/常量/FakeBackend
├── docs/
│   ├── DESIGN.md                    本文档
│   └── proposals/                   特性设计文档（P000 流程）
├── ROADMAP.md                       跟踪索引（单一事实源）
├── requirements.txt                 一键安装入口（-e .[dev]；依赖事实源在 pyproject）
├── NOTICE                           Harbor Apache 2.0 血缘致谢
└── pyproject.toml                   依赖: pydantic + pyyaml + typer + claude-agent-sdk（硬依赖，SDK 自带 CLI）
```

五份 prompt/rubric 资产（analyze 系列 3 + check 系列 2）**逐字节冻结**于上游原版（`tests/test_assets.py` 以 sha256 快照守卫），保证资产溯源与对上游 diff 的可同步性；`KNOWN-ISSUES.md` 与未来家族 rubric 不在冻结范围。

---

## 六、CLI 与触发方式

### 实际命令形态（全部经 `--help` 与 E2E 核验）

```bash
# 单 trial 归因（Anthropic 官方端点，模型默认 haiku）
triage analyze <trial_dir>

# DeepSeek 等 Anthropic 兼容端点（环境变量指端点 + -m 指模型）
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
triage analyze <trial_dir> -m deepseek-flash

# job 级批量归因（--failing 只筛 badcase；空集时零 LLM 调用短路退出）
triage analyze <job_dir> --failing -m deepseek-flash

# 并发（-j）+ 中文报告（--lang zh：analysis.md 即中文原生撰写版）
triage analyze <job_dir> --failing -m deepseek-flash -j 8 --lang zh

# 跨机器拷贝场景：手动覆盖 task 目录位置
triage analyze <trial_dir> --task-dir /local/path/to/task

# 自定义判定标准（analyze 侧接受 rubric 文件路径）
triage analyze <trial_dir> --rubric my-rubric.toml

# 任务质量检查（check 侧 -r 接受文件路径或家族名；家族文件当前仅有 default）
triage check <task_dir>                       # 默认 check-default.toml，模型默认 sonnet
triage check <task_dir> -r deep-swe           # 家族名解析 → assets/check/rubrics/check-deep-swe.toml（P002）

# 复原：递归删除 triage-kit/ 产物目录（默认 dry-run，--yes 才真删；锁定目录点名跳过，其余照删）
triage clean <job_dir>                        # 预览
triage clean <job_dir> --yes                   # 实际删除，原生评测数据零损伤
```

各命令通用：`--force/-f` 绕过缓存重跑；`--verbose/-v` 开 DEBUG 日志（`[trial_name]` 前缀归因并发下的日志行）。

**并发说明**（P003）：`triage analyze` 的 job 模式支持 `-j/--jobs <n>` 有界并发（`ThreadPoolExecutor(max_workers=n)` 包裹逐 trial 分析，默认 `-j 1` 保持串行行为）。产物顺序钉在目录序上，对 `j` 不变；并发下日志带 `[trial_name]` 前缀可归因；单 trial 失败不毒化兄弟（计入 `failed_trials` 并打 ERROR 行）。注意 worker 是 SDK CLI 子进程（每 trial 一个），`-j` 取值需兼顾机器资源。限流由用户自行调低 `-j` 应对（无自动限流调度）。

**环境变量**：
- `ANTHROPIC_API_KEY`（凭证，Anthropic 官方或兼容端点的 key）
- `ANTHROPIC_BASE_URL`（端点覆盖：Anthropic 官方为默认值；DeepSeek 等兼容端点设为其 anthropic 兼容地址）

### TRAE skill 形态（P001，未实现）

无命令、无运行时——规划为 `backends/trae/SKILL.md` 资产包，放入 TRAE skills 目录后对话触发。TRAE agent 天然具备 Read/Glob/Grep，按 SKILL.md 规程读取同一份 assets/ 资产执行，产出同格式文件。

---

## 七、产物布局与缓存语义

对 job 目录跑完后：

```
<job_dir>/                                       ← job 目录
├── triage-kit/                                  job 级产物目录
│   ├── analysis.json                            job 级聚合（恒英文）
│   ├── analysis.md                              job_summary 文本版（语言随 --lang）
│   ├── analysis.meta.json                       缓存身份 sidecar
│   └── run.log                                  本次运行执行日志（恒 DEBUG、覆盖式，P011）
└── ts-pattern-match-each__9giF4pL/
    ├── result.json                              （原有，只读）
    ├── agent/trajectory.json                    （原有，只读——judge 的证据源）
    └── triage-kit/                             trial 级产物目录（单 trial 直调时含 run.log）
        ├── analysis.json                        单 trial 归因（恒英文）
        ├── analysis.md                          人读版（语言随 --lang）
        └── analysis.meta.json                  缓存身份 sidecar
```

**check 产物**同规则：`<task_dir>/triage-kit/check-result.json` + `check-result.meta.json` + `run.log`。
**run.log 落点**（P011）：`<CLI 参数目录>/triage-kit/run.log`——单 trial 直调落 trial 级，job 模式落 job 级（一份，`[trial_name]` 前缀归因），check 落 task 级；`triage clean` 随目录一并复原。

**缓存语义**：
- 身份 = sidecar 记录的 **rubric 内容 sha256 + model**。匹配 → 复用（含 schema 回验）；不匹配 → 报错提示 `--force`；无 sidecar（legacy 平铺产物）→ 视为 miss 重跑覆盖
- `--failing` 且全部通过（无 badcase）→ **空集短路**：0 次 LLM 调用、不写产物、exit 0
- 单 trial 失败不中断 job：进 `failed_trials` 聚合后继续
- 缓存命中路径不会自动补齐新版式产物（升级功能后需 `--force` 或手动补齐）

**judge 禁读机制（防自引用锚定，2026-10-09 实证引入）**：`--force` 重跑时 judge 若能读到上一轮判定，独立性失效。现状：
1. check 的 file_tree 渲染排除 `triage-kit/`（`render_file_tree(exclude=...)`）——check 侧已封堵
2. **analyze 侧已知缺口（P013 立项待办）**：claude 后端将工具执行委托给 Agent SDK（`bypassPermissions`），CLI 的 Read/Glob/Grep 不经过本地沙箱，`triage-kit/` 旧产物对 judge 可见——候选方案是 CLI permissions deny 规则，Gate 1 时定稿

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

judge 的响应 trial_name 必须与 trial 目录名一致，不一致按失败处理；空 summary 拒收。

**check 与 analyze 的业务闭环**：check 的 `behavior_in_task_description`（考了没写）是 analyze 的 `task_specification`（失败归因于任务缺陷）在**评测前**的镜像——上游拦住的缺陷正是下游归因时要剥离的噪声。

---

## 八、数据流

**analyze（trial 侧归因）**：

```
用户触发 → trial_reader 朴素读 result.json（筛 badcase / 判定 trial vs job 目录）
        → analyzer 渲染 prompt（assets 模板 + rubric 编译产物 guidance/schema；
          task 目录可用时挂为 add_dir，不可用时注入降级话术——跨机器拷贝场景这是主路径）
        → backend（claude harness）执行 agent 循环，返回 (result, meta)
        → schema 校验（trial_name 一致性 + 空值拒绝）→ analysis.json/meta 落盘 triage-kit/ 子目录
          （analysis.md 语言随 --lang：en=机械渲染（零 LLM 调用）；
            zh=中文原生撰写二跳——一次纯 LLM query，输入为结构化 payload
            （trial 级 analysis.json 内容 / job 级 summary），判定结论与 JSON
            一致是硬约束，直接落为 analysis.md）
        → job 模式：所有 trial 经有界线程池（-j/--jobs，默认 1=串行 FIFO）→ join 后按目录序折叠
          → 二级聚合（各 trial summary + checks 拼接，无工具纯 LLM 调用）
```

**check（task 侧质检）**：

```
用户触发 → task_reader 校验 task 目录（task.toml + environment/ 存在性；steps/ 存在时校验
          至少含一个有效 step 目录——注意：当前为整体单次检查，逐 step 展开未实现）
        → checker 渲染 prompt（file_tree 排除 triage-kit/ + criteria_guidance 注入）
        → backend 执行 agent 循环，返回 (result, meta)
        → schema 校验 → triage-kit/check-result.json + sidecar 落盘
```

---

## 九、rubric 家族机制与质量优化机制

### 1. rubric 家族机制（数据驱动的定制化扩展）

rubric 本身是纯数据（TOML），针对特定数据集家族做定制 rubric 是**零架构成本**的一等扩展——`load_rubric` + `-r` 参数天然支持。

- **当前实现**：check 侧 `-r` 接受文件路径或家族名（`check-<family>.toml` 解析约定），analyze 侧 `--rubric` 接受文件路径；已 shipped 的家族文件仅 `check-default.toml`（deep-swe 家族为 P002）
- **家族自动探测**（按目录特征）：未实现，未排期
- **合并策略**：先整体替换，后按需引入继承——家族 rubric 先做成完整独立 TOML（结构重复可容忍，rubric 文件很小）；待出现第三个家族、重复维护成为真实痛点时，再给 `load_rubric` 加 `base` 继承合并——届时有两个真实家族样本可参照设计合并语义，优于凭空预设
- **deep-swe 家族版的原则**（P002 落地时遵循）：只修 guidance 文本层（把已知误判指纹写死），**不动 criteria 结构**——保持与 default 逐条可对照

### 2. KNOWN-ISSUES backlog（rubric 质量优化机制）

rubric 设计质量的欠账**不靠预先重写偿还**，而是文档化修改点、真实 badcase 驱动逐步优化：`assets/check/rubrics/KNOWN-ISSUES.md` 记录每条已知缺陷 + 证据案例（基于 2026-10-08 对 DeepSWE 113 个真实任务的逐条审读），要点：

- **#4 tests_or_solution_in_image**：guidance 未覆盖双镜像分离模式（environment/Dockerfile 干净 + tests/Dockerfile 烤入测试是合法设计）
- **#5 test_deps_in_image**：未覆盖"树外安装（/opt）保持 /app 字节一致"的防作弊模式
- **#7 pinned_dependencies**：guidance 以 Python 为中心，未抽象为语言无关原则
- **#11 file_reference_mentioned**：严格度未按任务形态校准（SWE 任务惯例是 agent 自行探索入口文件）
- **#3 anti_cheating_measures**：存在性检查 ≠ 质量检查，对高工程化数据集无辨别力

优化节奏：某次 check 误判 → 修对应 guidance → KNOWN-ISSUES.md 记录案例闭环，不提前空想。

### 3. 确定性前置层（设计方向，未排期）

check 对 DeepSWE 类任务最有价值的检查是**契约自洽性**（f2p/p2p node-id 与 test.patch 匹配、config.json 报告路径与 test.sh 产出路径一致等）——这些是**确定性可验**的，不适合塞进 LLM rubric。规划形态：家族伴生确定性脚本（如 `core/contract_checks.py`），先跑确定性校验、结果注入 LLM 检查上下文，LLM 只处理真正需要判断的部分。契合既有评测哲学：**确定性、低延迟的检查做 CI 门禁，LLM 判断做趋势分析**。当前仅在架构上为 checker 管线留出"前置层"位置，未实现、未立项。

---

## 十、工程质量机制

- **TDD**：全项目红-绿流程，测试先行（137 项，pytest）；共享工厂/常量/FakeBackend 集中于 `tests/conftest.py`，杜绝测试间重复
- **冻结资产守卫**：五份 prompt/rubric 资产 sha256 快照测试，任何字节级改动即刻报警（资产溯源与上游 diff 可同步性的根基）
- **纯测试性**：`core/` 零 LLM 依赖，analyzer/checker 编排全部由 FakeBackend 驱动测试，不碰真实端点；真实端点验证走实测 E2E（DeepSeek anthropic 兼容端点，含 113-trial 真实 job 复跑）
- **上下文与预算由 SDK 承担**：工具循环、轮次预算、上下文压缩均由 Claude Code CLI 自管（P012 的核心收益——自研 harness 的 forcing-400 / 工具异常两类缺陷随 general 退役消失，相关 dropped 条目文档已删除）

---

## 十一、边界与已知取舍

- **多步任务逐 step 展开未实现**：`task_reader` 能检测 steps/ 并校验，但 `checker` 为单次整体检查——对多步任务存在与上游原版相同的盲区（根目录 instruction/tests 为空时部分 criteria 失去判定对象）。待立项（P004）
- **analyze 侧 judge 禁读缺口**：judge 禁读机制（第七节）在 claude 路径上失效——CLI 工具不经本地沙箱，`triage-kit/` 旧产物对 judge 可见（P013 立项待办）
- **并发无限流调度**：`-j/--jobs` 为固定线程数，无限流自动退避——限流由用户调低 `-j` 自理（非目标，见 P003）；且 worker 为 CLI 子进程，`-j` 过高会吃满机器资源
- **模型身份不进聚合**：trial 的 agent/model 身份（result.json 的 `config.agent.*`）未进入 job 聚合 prompt——聚合模板第 6 点"agents/models 差异"在多 agent job 下无数据可用，LLM 只能声明无法比较（P007 立项待办）
- **非 Anthropic 官方模型的 meta 缺失**：兼容端点（如 DeepSeek）不回填 token usage，`AgentMeta` 的 token 计数为 None、`analysis.meta.json` 无 token 统计（不影响判定与缓存身份，cost 由 CLI 回填）
- **中文报告为翻译体**：（P009 已修复并升级为路线 B）曾为英文报告的逐句翻译（`analysis.zh.md` 双文件形态）；现 `--lang zh` 直接以中文原生撰写生成 `analysis.md`（判定与 JSON 一致、标识符保留英文，JSON 契约产物恒英文）
- **运行日志不落盘**：（P011 已修复）执行日志现持久化到 `<CLI 参数目录>/triage-kit/run.log`（恒 DEBUG、覆盖式，控制台行为不变），随产物同生共死，`triage clean` 一并复原
- **缓存命中不补齐新产物**：功能升级新增产物文件后，旧缓存目录需 `--force` 或手动补齐
- **task 目录跨机失效是主路径**：Linux 产出的 result.json 拷贝到 Windows 后 task path 必然不可解析，task_section 的降级话术（"infer from trajectory"）在跨机场景是常态而非边缘；DeepSWE 样本中 mini-swe-agent 轨迹内嵌完整任务 prompt，降级路径实测可用，但不具普遍性
- **job 模式不透传 --task-dir**：一个 job 的多个 trial 可能来自不同任务，单一路径无法覆盖
- **assets 解析假定 editable 安装**：`core/assets.py` 以包位置回溯仓库根的 `assets/`，仅在 `pip install -e` 下成立；发布 PyPI 前需改为包资源解析（`importlib.resources`）并将 assets 声明为包数据
- **rubric 质量的既知局限**：default rubric 为标准 Harbor 模板任务设计，对高工程化数据集存在已知误判点（#3/#4/#5/#7/#11，详见 KNOWN-ISSUES）；check 的真实价值场景是**新任务入库门禁**，而非给成熟数据集复检
- **check 文案与上游的可同步性**：check.txt 仅改首句的项目名（改为 "a Harbor task"），其余逐字节保留，将来 Harbor 上游 rubric/prompt 更新可 diff 同步
- **血缘法律留痕**：NOTICE 注明资产派生自 Harbor（Apache 2.0），assets 内容逐字节保留，命名层完全独立
