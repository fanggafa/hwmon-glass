## 液态玻璃硬件监控 v1.1.0

Windows 系统托盘硬件监控面板，iOS 26 液态玻璃风格。**开箱即用，无需安装 Python。**

![panel](https://raw.githubusercontent.com/fanggafa/hwmon-glass/main/docs/panel.png)

---

### 本次更新

**新增设置窗口** —— 点齿轮图标或托盘右键菜单打开：

- 面板透明度调节（40%–100%，实时生效）
- 刷新间隔（0.5–5.0 秒）
- 开机自动启动
- 配置保存到程序同目录的 `settings.json`

![settings](https://raw.githubusercontent.com/fanggafa/hwmon-glass/main/docs/settings_sheet.png)

**修复**

- 托盘左键点击无响应（`left_click` 参数误写成 `None`）
- 托盘图标启动方式（改用独立线程 `run()`）
- 托盘菜单各项回调全部接通
- 加入单实例保护，避免提权重启产生双进程

**体积**

本版起 CI 统一使用 Python 3.10 构建，单文件从 33.8MB 回到约 27MB。

---

### 下载

| 文件 | 说明 |
| --- | --- |
| `LiquidGlassMon.exe` | 单文件程序，约 27MB，双击运行 |
| `SHA256SUMS.txt` | 校验值 |

### 使用

1. 下载 `LiquidGlassMon.exe`
2. **双击运行** —— 首次启动会请求管理员授权
3. 若未安装温度驱动，程序会弹出引导窗口，点「立即安装」即可
4. 面板出现在屏幕右下角

> 单文件已包含 Python 运行时、全部依赖、传感器库、驱动安装包。
> 唯一的例外是内核驱动本身 —— Windows 要求它必须经 UAC 提权安装，
> 程序会自动引导你完成这一步。

### 托盘操作

| 操作 | 效果 |
| --- | --- |
| 左键单击 | 显示/隐藏面板 |
| 右键 | 菜单：显示面板、图标指标切换、硬件详情、设置、退出 |

> Windows 11 默认把新图标折叠进「^」。把它拖到任务栏即可常驻。

### 能读到什么

| 项目 | 无需驱动 | 需要 PawnIO 驱动 |
| --- | :---: | :---: |
| CPU 占用 / 频率 / 线程 | ✅ | |
| GPU 占用 / 显存 | ✅ | |
| 显卡温度 / 热点 | ✅ | |
| 硬盘温度 | ✅ | |
| 内存 / 磁盘 / 网络 | ✅ | |
| **CPU 温度** | | ✅ |
| **主板温度** | | ✅ |

驱动由程序内置并一键安装，无需手动下载。

### 已知限制

- **内存温度**需要内存条 SPD 传感器支持，多数消费级内存没有
- **显卡温度**依赖厂商驱动，虚拟机 / 远程桌面下可能读不到
- 天气功能尚未实现

### 校验

```powershell
Get-FileHash LiquidGlassMon.exe -Algorithm SHA256
```

---

**许可**：代码 MIT。内置的 [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) 为 MPL-2.0，[PawnIO](https://github.com/namazso/PawnIO) 为独立开源驱动。

**完整变更**：见 [CHANGELOG.md](https://github.com/fanggafa/hwmon-glass/blob/main/CHANGELOG.md)
