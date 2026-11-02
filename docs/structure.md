# 项目结构

## 仓库布局

```text
.
├── main.py                      网页启动入口
├── src/
│   ├── projects.py              工程管理命令入口
│   ├── build_sprites.py         分阶段处理命令入口
│   ├── build_dafeiyu_sprites.py  指定默认工程的处理入口
│   ├── check_sprite_architecture.py  Python 包依赖检查
│   ├── texturepacker.py         图集元数据的兼容导入入口
│   ├── requirements-workbench.txt    网页及命令行依赖
│   ├── requirements-sprites.txt      命令行图像处理依赖
│   └── sprite_pipeline/         主要实现，见下表
├── tests/                      Python、JavaScript 与浏览器测试
├── workspaces/                 本机素材工程
├── images/                     界面截图
├── docs/                       项目结构、操作命令与设计理念
├── README.md                   项目简介与安装启动
└── pyproject.toml              Python 静态检查配置
```

`branch_docs/` 保存旧文档归档；当前说明从根目录 README 进入。

## 代码职责

`src/sprite_pipeline/` 按职责组织：

| 目录 | 内容 |
| --- | --- |
| `domain/` | 资源引用、动作展开、播放时长、身份与数值校验等规则 |
| `imaging/` | 原图切割、图像缩放、锚点对齐、PNG 与 GIF 编码 |
| `storage/` | 配置与文件读写、切片缓存、稳定身份、工程锁、历史恢复与图集元数据 |
| `application/` | 工程操作、预览与增量处理、动作导出、后台任务及结果检查 |
| `interfaces/` | HTTP 路由、工程 CLI 和分阶段 CLI 的参数与结果转换 |
| `web/` | 原生 HTML、CSS、JavaScript 界面与 Canvas 播放器 |

包根目录中的 `config.py`、`workbench.py`、`server.py` 等模块保留兼容导入；具体实现位于上述子包。

## 素材工程布局

新建工程位于 `workspaces/<工程ID>/`。工程 ID 是目录名，支持中文；配置中的 `paths` 决定实际素材与输出路径。

| 路径 | 用途 |
| --- | --- |
| `pipeline.json` | v2 配置：画布、锚点、切割与处理规则、资源编排、播放与 Review 设置 |
| `README.md` | 该工程的简短说明 |
| `source/` | 原始图片 |
| `references/` | 参考图片，也支持 GIF；旧工程的 `reference/` 仍可读取 |
| `source_sprites/` | 保留原始尺寸的切片及索引，可由原图与切割规则重建 |
| `processed_sprites/` | 可供动作引用的正式单帧；人工修图可放入 `imports/` 子目录 |
| `exports/` | 分阶段命令按需生成的帧序列、图集、预览及元数据 |
| `.sprite-workbench-history/` | 图片操作的本地恢复记录，执行相关操作后生成 |

网页和 `projects.py export` 在临时目录中生成 ZIP，不要求先生成工程内的 `exports/`。旧布局可通过网页启动参数 `--config` 直接打开。

[返回 README](../README.md) · [操作命令](commands.md) · [设计理念](design.md)
