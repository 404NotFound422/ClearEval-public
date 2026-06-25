# 论文本地编辑说明

本目录是一个示例论文模板，可在 VS Code 中配合 LaTeX Workshop 插件本地编辑，也可以与 Overleaf 同步使用。

## 本地编辑

1. 在 VS Code 中打开 `paper/main.tex`
2. 保存文件时 LaTeX Workshop 会自动调用 `latexmk` 编译
3. 编译生成的 PDF 会显示在右侧标签页
4. 双击 PDF 可反向定位到 LaTeX 源码位置

## 与 Overleaf 同步

### 方法 1：Git 同步（推荐）

1. 在 Overleaf 中打开项目 → Menu → Git
2. 复制 Git URL
3. 在本机克隆该仓库到本目录，或直接覆盖 `paper/` 内容
4. 使用 Git 提交/拉取/推送实现同步

### 方法 2：手动导入导出

- 在 Overleaf 中点击 Menu → Download Source，解压覆盖本目录
- 编辑后打包上传回 Overleaf

## 文件说明

- `main.tex`：论文主文件
- `references.bib`：参考文献数据库
- `sections/`：可存放分章节文件（使用 `\input{sections/xxx}` 引入）
- `figures/`：存放图片
- `.latexmkrc`：本地 latexmk 配置（不影响 Overleaf）

## 注意事项

- 如果论文为英文，可删除 `main.tex` 中的 `\usepackage[UTF8]{ctex}`
- 如需使用 `xelatex` 或 `lualatex`，在 VS Code 状态栏点击当前 Recipe 切换
