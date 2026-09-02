# vibe-coding 私有笔记同步 recipes。
# 复制这个文件的内容进你项目自己的 justfile（或者用 `import` 引入）。
# 新项目直接跑 `just vibe-notes-init`，不用手动判断有没有初始化过——已经建好会自动跳过对应步骤。

notes_branch := "notes/vibe-coding"
notes_dir := "notes"

# 启动 object gallery 可视化 web app（先扫描生成 manifest，再从 repo 根起静态服务）
gallery port="8891":
    #!/usr/bin/env bash
    set -euo pipefail
    python tools/object-gallery/gen_manifest.py
    echo "打开 http://localhost:{{port}}/tools/object-gallery/"
    python -m http.server {{port}}

# 启动 dataset viewer：并排检查每个 task 的 episode video 和它的 instruction 是否对得上
dataset-viewer port="8892":
    #!/usr/bin/env bash
    set -euo pipefail
    python tools/dataset-viewer/gen_manifest.py
    echo "打开 http://localhost:{{port}}/tools/dataset-viewer/"
    python -m http.server {{port}}


# 幂等初始化：远端没有 notes/vibe-coding 分支就建，.gitignore 没排除 notes/ 就加，
# 然后拉取本地笔记仓库。已经初始化过的项目重复运行是安全的，会跳过已完成的步骤。
vibe-notes-init:
    #!/usr/bin/env bash
    set -euo pipefail

    if git ls-remote --exit-code --heads origin {{notes_branch}} > /dev/null 2>&1; then
        echo "[skip] 远端已存在 {{notes_branch}} 分支"
    else
        echo "[init] 创建 {{notes_branch}} 孤儿分支"
        current_branch=$(git symbolic-ref --short HEAD)
        git checkout --orphan {{notes_branch}}
        git rm -rf . > /dev/null
        git commit --allow-empty -m "init {{notes_branch}} orphan branch"
        git push origin {{notes_branch}}
        git checkout "$current_branch"
    fi

    if grep -qxF "/{{notes_dir}}/" .gitignore 2>/dev/null; then
        echo "[skip] .gitignore 已排除 /{{notes_dir}}/"
    else
        echo "[init] 追加 /{{notes_dir}}/ 到 .gitignore"
        echo "/{{notes_dir}}/" >> .gitignore
        git add .gitignore
        git commit -m "ignore local vibe-coding notes checkout"
    fi

    just vibe-notes-pull

# 拉取/初始化本地笔记（notes/.git 不存在则 clone，存在则 pull）
vibe-notes-pull:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d "{{notes_dir}}/.git" ]; then
        git clone --single-branch --branch {{notes_branch}} $(git remote get-url origin) {{notes_dir}}
    else
        cd {{notes_dir}} && git pull
    fi

# 提交并推送笔记改动
vibe-notes-push:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{notes_dir}}
    git add -A
    git commit -m "update vibe-coding notes" || echo "nothing to commit"
    git push