# CHANGELOG

All notable changes to this project should be documented in this file.

## [v1.1.2] - 2026-04-11

- 重构热力图逻辑，将参数解析与数据构建从 `main.py` 提取到 `heatmap.py`。
- 优化热力图 SVG 样式，修正边缘模糊和标签重叠问题。

## [v1.1.1] - 2026-04-11

- 更新插件元数据，补充主页、文档链接、许可证和标签信息。
- 支持 `/rkc` 全能榜结果以图片形式发送。
- 新增 `/map` / `/热力图` 指令，支持个人与社团当前月与全年度 GitHub 风格活跃热力图。
