# Obsidian 快速记录中心（Win顺 插件）

在 Win顺 搜索框中完成 Obsidian 笔记记录、待办添加、日记/收集箱打开、标题搜索和模板创建。插件为 Python `once` 脚本，无常驻进程、无第三方依赖、无网络请求。

## 命令

| 命令 | 用法 | 行为 |
|---|---|---|
| `note` | `note Vue3 生命周期` | 第一项预览后追加到收集箱；同时搜索标题匹配的 Markdown 文件 |
| `note` | `note --search Vue3` | 只搜索标题，不显示快速记录项 |
| `note` | `note --vault 2 学习 Three.js` | 指定 Vault 2 作为记录位置 |
| `note` | `note --template` | 列出默认 Vault 的 Templates 目录中的模板 |
| `note` | `note --template 会议纪要 --title 项目周会` | 选择模板并用指定名称创建笔记 |
| `todo` | `todo 完成 BufferGeometry 笔记` | 预览后追加到待办文件 |
| `daily` | `daily` | 打开今日日记；不存在时确认后创建 |
| `inbox` | `inbox` | 打开收集箱；不存在时确认后创建 |

也支持中文别名：`记录` / `笔记`、`待办`、`日记`、`收集箱`。

### 快速记录与标题搜索

输入 `note Vue3 生命周期` 会同时显示：

1. “记录到收集箱”结果，预览里显示将要写入的 Markdown；按 Enter 才真正写入。
2. 标题匹配结果；按 Enter 打开已有 Markdown 文件。

笔记默认追加到 `Inbox/收集箱.md`，格式为带时间标题的 Markdown 区块。待办默认追加到 `Tasks.md`，附带日期、时间和来源标记。成功后默认通过 Windows 的 `.md` 文件关联打开目标文件；建议把 `.md` 默认应用关联为 Obsidian。

## 设置
> 5 个位置（笔记目录、日记目录、收集箱文件、待办文件、模板目录）都可自定义，填 Vault 内的相对路径；绝对路径和 `..` 会被拒绝。想存到 Vault 外，把目标文件夹设为 Vault 2/3，再用 `--vault 2` 或 `--vault 3`。


在 Win顺 → 设置 → 插件 → Obsidian 快速记录中心中配置：

- **Vault 1**：必填，主 Vault 根目录。
- **Vault 2 / Vault 3**：可选。标题搜索跨所有已配置 Vault；快速记录会为每个配置的 Vault 分别提供一条结果。
- **默认记录位置**：`daily`、`inbox` 和模板创建使用默认 Vault；`note`、`todo` 可用 `--vault 2` / `--vault 3` 指定。
- 笔记目录：`Notes`
- 日记目录：`Daily`
- 收集箱文件：`Inbox/收集箱.md`
- 待办文件：`Tasks.md`
- 模板目录：`Templates`
- 自动识别代码片段、添加来源和时间、保存后打开笔记：均可开关。

上述目录均为相对于 Vault 根目录的路径。插件会拒绝绝对路径和 `..` 路径，并检查解析后的目标仍位于 Vault 内。

## 模板

把 `.md` 模板放入默认 Vault 的 `Templates` 目录。支持以下占位符：

- `{{title}}`：新笔记标题
- `{{date}}`：本地日期 `YYYY-MM-DD`
- `{{time}}`：本地时间 `HH:MM:SS`
- `{{datetime}}`：本地日期时间
- `{{source}}`：`Win顺`

模板创建默认保存到 `Notes` 目录；创建时会为缺少字段的 YAML frontmatter 自动补上标题、日期、创建时间和来源。若文件名已存在，会追加时间戳，不覆盖已有文件。`daily` 新建日记时会优先使用 `Templates/日记.md`、`Templates/Daily.md` 或 `Templates/daily.md`；找不到时使用内置日记模板。

## 自动代码块与重复检查

自动识别规则覆盖 Python、TypeScript、JavaScript、Java、C++、SQL、Bash 和 JSON 的常见特征。已存在 Markdown 围栏的内容不会重复包裹；对不确定的文本不做自动包裹。

普通 `note` 输入在按 Enter 保存动作时进行重复检测，不在每次键入时全量扫描。检测为规范化后的精确子串匹配，最多检查 600 个 Markdown 文件、单文件 192 KiB；内容短于 12 个字符不做跨库重复检测。发现疑似重复时不会直接写入，插件会展示已有文件，并提供“仍然保存”选项。待办重复检测针对目标待办文件。

## 权限与隐私

只声明：

- `files:read`：读取已配置 Vault 中的 Markdown 文件名、模板内容，以及保存前的重复检查内容。
- `files:write`：在已配置 Vault 中创建/追加 Markdown 文件。

不申请网络、剪贴板、进程启动、UI、通知或管理员权限。插件不上传任何 Vault 内容，不调用云端模型。

**沙箱说明：** 插件使用 `sandbox: normal`，因为 Win顺 的 `strict` 沙箱无法写入用户目录中的 Obsidian Vault。Win顺 的 `files:read` / `files:write` 是权限声明；官方文档说明 `files:write` 只有在 `strict` 下才可强制限制，而 `strict` 又不能写用户 Vault。因此请只安装并启用你信任的插件源码。插件会在代码层把文件路径限制在你配置的 Vault 根目录内，但这不是 Windows 强制隔离。

## 数据与运行依赖

- Windows 10/11 x64（具体宿主兼容性由 Win顺 版本决定）
- Win顺，建议 0.22.0 或更新版本
- Python 3（Win顺 能检测到的 Python 3）
- 仅 Python 标准库；没有 `pip install` 步骤
- 插件本身不在 Vault 之外保存用户笔记或密钥；Win顺 插件运行数据目录不用于存放笔记

本包的 `winshun.py` 是满足本插件所需的一次性模式 API 的轻量兼容适配层，并和官方 SDK 一样提供 `debug()`（写 stderr，进 `plugins.log` 和开发者模式的消息记录）。

也可以直接换成 Win顺「新建插件」模板附带的官方 `winshun.py`：`dispatch()` 会把官方 SDK 返回的 `ActionRequest` 对象（`action` / `item` / `command` / `text` 四个属性）归一化成 dict，再交给 `action_result()`，所有保存动作照常可用。本插件用到的公开接口（`query`、`settings`、`is_action`、`action_request`、`item`、`reply`、`effects`、`debug`）与官方一次性 SDK 一致。

## 安装与开发

1. 解压本目录。
2. 放到 `%LOCALAPPDATA%\WinShun\plugins\888bik.obsidian-quicknote\`，或在 Win顺 插件设置中导入本地插件包。
3. 在插件设置里配置至少一个 Vault，然后开启插件并确认文件读写权限。
4. 把 `.md` 默认打开应用设置为 Obsidian（可选，但推荐）。
5. 在开发者模式中输入 `note 测试`、`todo 测试任务`、`daily`、`inbox` 测试。

从源码构建的 Win顺 项目可运行：

```powershell
wsbench --plugin .\obsidian-quicknote --query "note Vue3 测试" --setting vault_1="D:\Notes\MyVault"
wsbench --plugin .\obsidian-quicknote --query "todo 测试待办" --setting vault_1="D:\Notes\MyVault"
wsbench --plugin .\obsidian-quicknote --query "daily" --setting vault_1="D:\Notes\MyVault"
```

## 失败处理与安全行为

- Vault 路径未配置、目录不存在、路径越界、模板不存在、目标不是普通文件或文件过大时，会返回明确错误，不伪造成功结果。
- `daily_folder`、`inbox_file`、`todo_file`、`notes_folder` 等配置项必须是 Vault 内的相对路径；填绝对路径会返回「路径必须是 Vault 内的相对路径」，不会让进程崩溃。
- 任何未预期的异常都会转成一行「操作失败：…」的结果，同时把细节写进 stderr（`plugins.log`）。
- 查询阶段不创建文件、不追加内容、不打开应用、不修改剪贴板。
- 文件创建采用独占模式，避免覆盖同名文件；追加前检查文件大小。
- 笔记和待办写入失败时保留窗口并显示错误信息。
- 本插件不会删除文件，也不会自动覆盖已有笔记。

## 测试

在插件目录执行：

```powershell
python -m unittest discover -s tests -v
```

测试覆盖输入解析、代码识别、重复检测、路径穿越拦截、文件创建和追加、协议 JSON 输出，以及 `dispatch()` 异常降级、官方 SDK `ActionRequest` 兼容；当前 26 个测试。真实 Win顺 消息记录和 `wsbench` 往返需要在安装 Win顺 的 Windows 环境中验证。

## 更新记录

- 1.0.2：查重不再读取 Vault 外的目录链接文件；`safe_filename` 也拦截 `con.txt` 这类带扩展名的设备名；新建文件遇到同名时提示「已存在，未覆盖」，不再谎报成功。

## 许可证

MIT License，见 `LICENSE`。
