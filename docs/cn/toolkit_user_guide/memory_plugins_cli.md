# AgentArts Memory AI Agent插件安装指南

## 概述

通过 `agentarts memory install` 命令可插将 AgentArts Memory 插件安装到AI Agent。安装后，Agent 在对话过程中自动将记忆写入AgentArts Memory，并在每轮对话前搜索并注入相关记忆，实现跨会话记忆持久化。

对应的卸载命令 `agentarts memory uninstall` 会移除插件自身的文件和配置，保留用户原有的其他设置。

## 环境要求

- Python 3.10+
- 已安装 AgentArts SDK：`pip install agentarts-sdk>0.1.5`
- 已安装 Hermes/ Codex / Claude Code / OpenCode 其中任意一款多款Agent

## 凭据配置

安装时需要提供三个凭据，通过环境变量传入：

| 环境变量 | 说明 | 是否必填 |
|---|---|---|
| `AGENTARTS_MEMORY_SPACE_ID` | AgentArts Memory Space ID（>= 8 字符） | 是 |
| `HUAWEICLOUD_SDK_MEMORY_API_KEY` | Memory API Key（>= 16 字符） | 是 |
| `HUAWEICLOUD_SDK_REGION` | 华为云区域（如 `cn-southwest-2`） | 否，默认 `cn-southwest-2` |

### 凭据获取

1. 登录华为云 AgentArts 控制台
2. 创建 Memory Space，获取 Space ID
3. 在"访问密钥"页面创建 API Key

### 凭据传入方式

`agentarts memory install`执行安装，安装器检测到全部变量会展示现有配置并询问是否沿用。

**交互式输入**

如果环境变量未设置，安装器会在交互模式下逐个提示输入。输入的 API Key 在回显时掩码显示为前 6 位 + `***` + 后 4 位，Space ID 和 Region 完整显示。

**凭据持久化**

如果用户在交互模式下修改了任一凭据（与已有环境变量不同），安装器会询问是否保存到 shell 配置文件：
- macOS / Linux：写入 `~/.zshrc` 或 `~/.bashrc`（`export KEY=value`）
- Windows：用 `setx` 写入用户环境变量


## 支持的平台

| 平台 | target 名称 | 配置目录（global） | 配置目录（project） | 是否需要 Node.js |
|---|---|---|---|---|
| Codex | `codex` | `~/.codex` | `.codex/` | 是 |
| Claude Code | `claude` | `~/.claude` | `.claude/` | 是 |
| Hermes Agent | `hermes` | `$HERMES_HOME` 或 `~/.hermes` | N/A（固定 user 级） | 否 |
| OpenCode | `opencode` | `~/.config/opencode` | `.opencode/` | 是 |

> Windows 下 Hermes 配置目录为 `%LOCALAPPDATA%\hermes`（由 Hermes 安装器设置 `HERMES_HOME` 环境变量）。

## 命令参数

### install

```bash
agentarts memory install [TARGET] [OPTIONS]
```

| 参数 | 简写 | 说明 | 默认值 |
|---|---|---|---|
| `TARGET` | 无 | 目标平台：`codex` / `claude` / `hermes` / `opencode`。省略则自动检测已安装的平台。 | 自动检测 |
| `--global` | 无 | 安装到用户级配置（全局生效）。省略则提示选择 project 或 global。 | False |
| `--yes` | `-y` | 自动确认所有提示（非交互模式）。 | False |

### uninstall

```bash
agentarts memory uninstall [TARGET] [OPTIONS]
```

| 参数 | 简写 | 说明 | 默认值 |
|---|---|---|---|
| `TARGET` | 无 | 目标平台。省略则列出已安装的平台供选择。 | 列表选择 |
| `--global` | 无 | 仅限 user 级安装。 | False |
| `--yes` | `-y` | 自动确认卸载提示。 | False |

## 安装流程

```
agentarts memory install
    |
    +--> 检测已安装平台（或使用指定的 TARGET）
    |
    +--> 检查凭据环境变量
    |       |
    |       +--> 全部存在 --> 展示配置（API Key 掩码）--> 询问是否沿用
    |       |                   |
    |       |                   +--> 沿用 --> 直接使用，跳过保存提示
    |       |                   +--> 覆盖 --> 逐个输入（现有值为默认）--> 有改动才提示保存
    |       |
    |       +--> 有缺失 --> 交互补全 --> 触发保存提示
    |
    +--> 选择安装范围（project 或 global，Hermes 固定 global）
    |
    +--> 执行平台适配器 install()
    |       |
    |       +--> 复制脚本/插件文件
    |       +--> 合并 hooks / MCP 配置到平台配置文件
    |       +--> 写入凭据到配置文件
    |
    +--> 记录到 ~/.agentarts/installed.json
    |
    +--> 输出安装结果
```

## 各平台部署内容

### Codex

| 部署内容 | 目标路径 |
|---|---|
| 3 个 .mjs hook 脚本 | `<config_dir>/agentarts-memory/scripts/` |
| hooks 定义（UserPromptSubmit + PreCompact） | `<config_dir>/hooks.json`（merge） |
| `[features] hooks = true` | `<config_dir>/config.toml`（merge） |
| MCP server 配置 + 凭据 | `<config_dir>/config.toml`（merge） |

### Claude Code

| 部署内容 | 目标路径 |
|---|---|
| 3 个 .mjs hook 脚本 | `<config_dir>/agentarts-memory/scripts/` |
| hooks 定义 + MCP server 配置 + 凭据 | `<config_dir>/settings.json`（merge） |

### Hermes Agent

| 部署内容 | 目标路径 |
|---|---|
| provider.py + plugin.yaml + \_\_init\_\_.py | `<hermes_home>/plugins/agentarts/` |
| 凭据（API Key / Space ID / Region） | `<hermes_home>/.env`（去重写入） |
| `memory.provider: agentarts` | `<hermes_home>/config.yaml`（merge） |

运行时还会创建日志文件 `<hermes_home>/logs/agentarts.logs`。

### OpenCode

| 部署内容 | 目标路径 |
|---|---|
| TS 插件 | `<config_dir>/plugins/agentarts-memory-capture.ts` |
| /recall 和 /remember slash 命令 | `<config_dir>/commands/` |
| plugin 注册 + MCP server 配置 + 凭据 | `<config_dir>/opencode.json`（merge） |

## 卸载行为

卸载时精确移除插件自身的文件和配置项，保留用户已有的其他设置：

- **Codex / Claude**：从 hooks.json / settings.json 中剥离自身 hooks 和 MCP 条目（剩余非空则写回），删除 scripts 目录，清理空目录。
- **Hermes**：删除插件目录，从 .env 中剥离三个凭据 key（剩余非空则写回），将 config.yaml 中 `memory.provider` 置空。
- **OpenCode**：从 opencode.json 中剥离 plugin 条目和 MCP 配置（剩余非空则写回），删除 TS 插件和命令文件，清理空目录。

卸载后从 `~/.agentarts/installed.json` 中移除对应记录。若无剩余安装，则删除 manifest 文件本身。

## 跨平台兼容

安装器已适配 macOS、Linux、Windows 三端：

- 路径分隔符：所有输出路径通过 `os.path.normpath` 统一为平台原生分隔符（Windows 为 `\`，Unix 为 `/`）
- MCP server 命令：使用 `sys.executable`（当前 Python 解释器的绝对路径），不依赖 `python3` 在 PATH 中
- TOML 配置：字符串值用 `json.dumps` 转义反斜杠，避免 Windows 路径破坏 TOML 语法
- 凭据持久化：macOS/Linux 写 shell rc，Windows 用 `setx` 写用户环境变量
- JSON hooks 模板：路径占位符替换后反斜杠统一转为正斜杠（Node.js 在 Windows 上兼容正斜杠）

## 使用示例

### 示例 1：自动检测并交互安装

```bash
agentarts memory install
```

安装器自动检测已安装的 AI Agent 平台，列出供选择，然后交互式引导凭据输入和范围选择。

### 示例 2：安装到 Claude Code（全局）

```bash
# 先设置环境变量
export AGENTARTS_MEMORY_SPACE_ID="my-space-12345"
export HUAWEICLOUD_SDK_MEMORY_API_KEY="abcdefghijklmnop123456"
export HUAWEICLOUD_SDK_REGION="cn-southwest-2"

# 安装
agentarts memory install claude --global
```

### 示例 3：非交互模式安装 Codex（项目级）

```bash
agentarts memory install codex --yes
```

`--yes` 模式下：跳过所有交互提示，凭据从环境变量读取（缺失则使用默认值），范围默认 project。

### 示例 4：安装 Hermes 插件

```bash
agentarts memory install hermes --global
```

Hermes 固定为 global 级安装，`--global` 参数可选。

### 示例 5：卸载

```bash
# 交互式选择要卸载的平台
agentarts memory uninstall

# 直接指定平台
agentarts memory uninstall codex --global --yes
```

### 示例 6：查看已安装的插件

安装记录存储在 `~/.agentarts/installed.json`，可直接查看：

```bash
cat ~/.agentarts/installed.json
```

## 安装后

安装完成后，重启对应的 AI Agent 平台即可生效：

- **Codex / Claude Code**：重启 CLI 工具，hook 脚本会在 UserPromptSubmit 和 PreCompact 事件时自动触发
- **Hermes Agent**：重启 Hermes，Provider 在 `initialize()` 时自动激活
- **OpenCode**：重启 OpenCode，TS 插件自动加载

## 注意事项

1. Codex 和 Claude Code 的 hook 脚本需要 Node.js 18+（使用 `fetch()` API）
2. 同一平台同一范围重复安装是幂等的——旧配置会被剥离后重新写入，不会产生重复条目
3. 卸载不会删除用户已有的其他 hooks、MCP server 或配置项
4. `~/.agentarts/installed.json` 是安装注册表，手动删除其中的文件不会自动清理已部署的插件文件（可使用 `agentarts memory uninstall` 的降级扫描功能定位残留文件）
5. Windows 下如果 `HERMES_HOME` 未设置，Hermes 配置目录默认为 `%LOCALAPPDATA%\hermes`
