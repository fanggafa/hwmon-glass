# 贡献指南

## 分支模型

```
main        受保护，只能通过 PR 合入
  └── feat/xxx    新功能
  └── fix/xxx     修复
  └── docs/xxx    文档
```

`main` 受分支保护规则约束：

- 必须通过 Pull Request 合入，不能直接 push
- CI 的 `test`、`lint`、`sanity` 三项检查必须全部通过
- 分支需与 main 保持同步

## 开发流程

```powershell
# 1. 从最新 main 开分支
git checkout main
git pull
git checkout -b feat/my-feature

# 2. 开发并本地验证
pip install -r requirements.txt pytest
python -m pytest tests -v

# 3. 提交
git add -A
git commit -m "feat: 简述改动"

# 4. 推送并开 PR
git push -u origin feat/my-feature
```

然后在 GitHub 上开 Pull Request，等待 CI 通过。

## 提交信息

采用 [Conventional Commits](https://www.conventionalcommits.org/)：

| 前缀 | 用途 |
| --- | --- |
| `feat:` | 新功能 |
| `fix:` | 修复 |
| `docs:` | 文档 |
| `refactor:` | 重构 |
| `perf:` | 性能 |
| `test:` | 测试 |
| `chore:` | 构建 / 工具 |

## 文档同步（强制）

**需求变更完成后，必须把关键点和注意事项写进对应文档，再提交 PR。**
代码改了而文档没跟上，PR 视为未完成。

改了什么，就更新哪里：

| 改动类型 | 必须更新的文档 |
| --- | --- |
| 新增 / 修改功能 | `README.md` 的功能表与用法；`CHANGELOG.md` 对应条目 |
| 新增设置项 | `README.md` 的设置说明；`RELEASE_NOTES.md` |
| 改了构建 / 打包方式 | `README.md` 的「自行打包」；`LiquidGlassMon.spec` 注释 |
| 改了发版流程 | `CONTRIBUTING.md` 的「发版」；`VERSIONING.md` |
| 新增传感器 / 数据来源 | `README.md` 的「能读到什么」表格 |
| 踩过的坑、非显然的取舍 | 写进相关模块的文档字符串，或在 `README.md`「技术要点」补一条 |
| 新增已知限制 | `README.md` 的「已知限制」；`RELEASE_NOTES.md` |

判断标准：**换一个人接手，只看文档能否不踩你已经踩过的坑。** 不能就要补。

PR 检查清单里有一项对应这条，提交前请逐项确认。

## 测试

```powershell
python -m pytest tests -v
```

`tests/test_core.py` 只测纯逻辑（格式化、评分、命名、命中测试），
不触碰 Windows API，因此在任何平台都能跑。

涉及 Win32 的代码（窗口、分层绘制、驱动）需要真机验证，PR 里请附截图。

## 发版

发版由**版本号变更**触发，不需要手动打 tag：

1. 按 [VERSIONING.md](VERSIONING.md) 的规则确定该升哪一位，修改 `hwmon/__init__.py` 的 `__version__`
2. 在 `CHANGELOG.md` 添加本次变更
3. 更新 `RELEASE_NOTES.md` 的标题与内容
4. 提交 PR

**版本号怎么升，以 [VERSIONING.md](VERSIONING.md) 为准**，速查：

| 情况 | 升哪一位 | 例 |
| --- | --- | --- |
| 只有修 bug | 第三位 | `1.1.0 → 1.1.1` |
| 新增功能，旧用法不变 | 第二位，第三位归零 | `1.1.1 → 1.2.0` |
| 不兼容变更 | 第一位，后两位归零 | `1.2.3 → 2.0.0` |
| 纯文档 / 纯 CI | 不升，不发版 | — |

PR 合入 main 后，`Release` 工作流会自动：

- 检测到版本号有变化（对应 tag 不存在）
- 跑测试
- 用 PyInstaller 打包单文件 exe
- 计算 SHA256
- 创建 GitHub Release 并上传产物

若版本号未变，工作流直接跳过，不会重复发版。
