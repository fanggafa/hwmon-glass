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

## 测试

```powershell
python -m pytest tests -v
```

`tests/test_core.py` 只测纯逻辑（格式化、评分、命名、命中测试），
不触碰 Windows API，因此在任何平台都能跑。

涉及 Win32 的代码（窗口、分层绘制、驱动）需要真机验证，PR 里请附截图。

## 发版

发版由**版本号变更**触发，不需要手动打 tag：

1. 在 `hwmon/__init__.py` 提升 `__version__`
2. 在 `CHANGELOG.md` 添加本次变更
3. 更新 `RELEASE_NOTES.md` 的标题与内容
4. 提交 PR

PR 合入 main 后，`Release` 工作流会自动：

- 检测到版本号有变化（对应 tag 不存在）
- 跑测试
- 用 PyInstaller 打包单文件 exe
- 计算 SHA256
- 创建 GitHub Release 并上传产物

若版本号未变，工作流直接跳过，不会重复发版。
