# Sprite Workbench

本地运行的 2D 精灵动画工作台。支持原图切割、画布与锚点对齐、逐帧调整、动作与序列编排，以及 PNG 帧、图集、WebP 和 GIF 导出。网页与命令行共用本机工程文件。

## 安装与启动

需要 Python 3.10+，建议使用虚拟环境。在仓库根目录执行：

```powershell
python -m pip install -r src/requirements-workbench.txt
python main.py
```

启动后自动打开浏览器，默认地址为 [http://127.0.0.1:8765](http://127.0.0.1:8765)。网页无需前端构建，也无需外部服务。工程默认保存在 `workspaces/`，可在网页中新建或打开。

仅使用命令行时，安装 `src/requirements-sprites.txt` 即可。更换端口、工程目录或直接打开配置文件，见操作命令文档。

## 项目文档

- [项目结构](docs/structure.md)：代码职责、入口和工程文件布局。
- [功能与操作命令](docs/commands.md)：网页功能、命令用途和常用参数。
- [配置与资源组合](docs/configuration.md)：JSON 输入、逐帧覆盖、动作槽位与 Review 格式。
- [设计理念](docs/design.md)：数据、编辑与导出的核心约定。
