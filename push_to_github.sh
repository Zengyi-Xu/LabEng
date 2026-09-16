#!/usr/bin/env bash
# 在 GitHub 网页新建 Zengyi-Xu/LabEng 仓库（不要勾选 README/.gitignore）后运行本脚本完成首次推送。
set -e
cd "$(dirname "$0")"
git remote add origin git@github.com:Zengyi-Xu/LabEng.git
git push -u origin main
echo "pushed."
