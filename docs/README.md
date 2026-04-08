# Docs

当前规范收敛为三层：

- `AI_CONSTITUTION.md`
  - 只放核心强约束。
- `docs/architecture.md`
  - 只放项目结构、运行模型和数据流规则。
- `docs/coding-rules.md`
  - 只放编码规范和文件布局规则。

详细文档继续按职责放在下列目录：

- `docs/architecture/`
- `docs/guides/`
- `docs/archive/`

任务流程不再写成 skills，统一改为按需使用的模板：

- `templates/implement.md`
- `templates/refactor.md`
- `templates/debug.md`
- `templates/review.md`

清理规则：

- 不再新增 `.codex/skills` 或 `.agents/skills` 作为项目规则入口。
- 不再新增 `docs/prompt.md` 这类一次性 prompt 文件。
- 当前有效约束来源只包括 `README.md`、`CLAUDE.md`、`docs/architecture*.md`、`docs/coding-rules.md`。
- `docs/guides/` 用于操作手册，不自动视为架构约束来源。
- 新文档进入对应目录；过期文档移入 `docs/archive/`。
