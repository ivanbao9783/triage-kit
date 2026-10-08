# Known Issues — check rubric backlog

已知缺陷 backlog，记录在 `check-default.toml` 逐条审读中发现的 guidance 设计问题。
基于 2026-10-08 对 DeepSWE v1.1 数据集（113 个真实 Harbor 任务）的对照审视，
证据案例取自 `ts-pattern-match-each` 等任务。

修复节奏约定：**真实 badcase 驱动**——某次 check 产生误判后，修对应 guidance，
并在对应条目下追加案例闭环记录；不做提前空想的修改。

## #3 anti_cheating_measures — 存在性检查 ≠ 质量检查

- **问题**：guidance 只判断"有没有防作弊措施"，不判断"防线之间是否自洽"。
  对高工程化数据集（DeepSWE 已有独立验证环境、断网、git 历史截断、构建自检
  tripwire 四层防线）必然 PASS，无辨别力。
- **影响**：对成熟数据集复检价值低；对简单任务仍有筛查作用。
- **方向**：家族 rubric（check-deep-swe）中增加契约自洽性维度，或由确定性
  前置层（见 DESIGN.md 第二批工作）承担。

## #4 tests_or_solution_in_image — 未覆盖双镜像分离模式

- **问题**：guidance 按"一个任务一个镜像"的世界观书写，未提及
  `environment/Dockerfile`（agent 用，干净）与 `tests/Dockerfile`（verifier 用，
  明文 COPY 测试）分离的合法模式。
- **证据**：ts-pattern-match-each 的 `tests/Dockerfile` 注释明示
  "the agent never sees this container"。
- **误判风险**：judge 扫到 tests/Dockerfile 的 COPY 即可能按字面判 FAIL。
- **方向**：deep-swe 家族 rubric 在 guidance 中写死该合法模式指纹。

## #5 test_deps_in_image — 未覆盖树外安装模式

- **问题**：guidance 把"agent 镜像内出现测试工具"一律视为泄漏信号；未覆盖
  "安装在仓库树外路径（如 /opt/...）以保持 /app 字节一致"的防作弊设计。
- **证据**：ts-pattern-match-each 的 environment/Dockerfile 将 jest CTRF
  reporter 装在 /opt/jest-ctrf，并以此维持针对 package.json 的防篡改
  tripwire 有效。
- **误判风险**：假阳性 FAIL。
- **方向**：同 #4，家族 rubric 写死指纹。

## #7 pinned_dependencies — 语言偏科

- **问题**：guidance 以 Python 生态为中心（只写 "pip install 须锁版本；
  apt 不用"），未抽象为语言无关原则。
- **影响**：对 TS（npm ci + lockfile）/ Go（go.mod）等生态，judge 需自行
  迁移规则，判定质量取决于 judge 能力。
- **方向**：guidance 改写为"依赖安装必须可复现"的语言无关表述，再列各
  生态的等价指纹（pip pin / npm ci+lockfile / go.mod / Cargo.lock）。

## #11 file_reference_mentioned — 严格度未按任务形态校准

- **问题**：guidance 隐含"数据产出型任务"标准（产出路径必须明说），
  但 SWE 任务的惯例是 agent 自行探索（如 instruction 说 "the package entry
  point" 而不写 src/index.ts 属正常）。
- **证据**：ts-pattern-match-each instruction 未写出入口文件路径，属合法。
- **误判风险**：judge 裁量空间大，同一任务多轮 check 结果可能不一致。
- **方向**：guidance 增加按任务形态分档的校准说明。

## 不修复项（记录原因）

- **#10 typos**：用 LLM 查拼写有误报专业术语的风险，且大半可由确定性
  拼写检查完成——长期应下沉到确定性前置层，而非改 guidance。
- **#9 structured_data_schema**：SWE 任务大多 not_applicable，是三值判定
  的正常表现，非缺陷。
