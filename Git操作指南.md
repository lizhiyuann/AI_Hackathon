# Git & GitHub 操作指南

## 一、首次提交新项目（从零开始）

### 1. 在 GitHub 网站创建仓库
- 打开 https://github.com/new
- 填写仓库名称（Repository name）
- 选择 Public 或 Private
- **不要勾选** "Add a README file"、".gitignore"、"License"（本地已有）
- 点击 "Create repository"

### 2. 在本地项目目录执行以下命令

```bash
# 进入项目目录
cd /home/lizhiyuan/project/你的项目名

# 初始化 Git 仓库
git init

# 创建 .gitignore（排除不需要提交的文件）
# 常见排除项见下方模板

# 添加所有文件到暂存区
git add .

# 创建首次提交
git commit -m "Initial commit: 项目描述"

# 设置主分支名称
git branch -M main

# 添加远程仓库地址（用 ghfast 加速）
# 格式: git remote add origin https://ghp_你的token@ghfast.top/https://github.com/你的用户名/仓库名.git
git remote add origin https://ghp_你的token@ghfast.top/https://github.com/lizhiyuann/仓库名.git

# 推送到 GitHub
git push -u origin main
```

---

## 二、已有项目日常提交

```bash
# 1. 查看当前状态（哪些文件被修改）
git status

# 2. 添加修改的文件
git add .                          # 添加所有修改
git add 文件名                     # 添加指定文件

# 3. 提交
git commit -m "描述你做了什么修改"

# 4. 推送到 GitHub
git push
```

### 提交信息规范建议
```
feat: 添加新功能
fix: 修复bug
docs: 更新文档
style: 代码格式调整
refactor: 重构代码
test: 添加测试
chore: 构建/工具变更
```
示例：`git commit -m "feat: 添加用户登录功能"`

---

## 三、常用 Git 命令速查

| 命令 | 作用 |
|------|------|
| `git status` | 查看文件状态 |
| `git log --oneline` | 查看提交历史（简洁版） |
| `git diff` | 查看具体修改内容 |
| `git remote -v` | 查看远程仓库地址 |
| `git branch` | 查看当前分支 |
| `git branch 分支名` | 创建新分支 |
| `git checkout 分支名` | 切换分支 |
| `git pull` | 拉取远程最新代码 |
| `git stash` | 暂存当前修改 |
| `git stash pop` | 恢复暂存的修改 |

---

## 四、.gitignore 模板

### Python 项目
```gitignore
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.env
*.log
.pytest_cache/
dist/
build/
*.egg-info/
```

### Node.js 项目
```gitignore
node_modules/
dist/
.env
*.log
.DS_Store
```

### 通用
```gitignore
# IDE 配置
.idea/
.vscode/
*.swp

# 系统文件
.DS_Store
Thumbs.db

# 敏感文件
.env
.env.local
credentials.json
```

---

## 五、你的 GitHub Token

> Token 存放在本地配置中，不在文档里明文记录。
> 远程仓库地址格式：`https://ghp_你的token@ghfast.top/https://github.com/用户名/仓库名.git`

### 查看当前远程地址
```bash
git remote -v
```

### 如果 token 过期
1. 打开 https://github.com/settings/tokens
2. 删除旧 token，重新生成
3. 更新远程仓库地址：
```bash
git remote set-url origin https://新token@ghfast.top/https://github.com/用户名/仓库名.git
```

---

## 六、完整操作流程图

```
创建新项目
    │
    ├─→ GitHub 网站创建仓库（不勾选任何选项）
    │
    ├─→ 本地: git init
    │
    ├─→ 创建 .gitignore
    │
    ├─→ git add .
    │
    ├─→ git commit -m "Initial commit"
    │
    ├─→ git branch -M main
    │
    ├─→ git remote add origin https://token@ghfast.top/https://github.com/用户/仓库.git
    │
    └─→ git push -u origin main


日常更新
    │
    ├─→ 修改代码
    │
    ├─→ git status（查看改动）
    │
    ├─→ git add .
    │
    ├─→ git commit -m "描述改动"
    │
    └─→ git push
```
