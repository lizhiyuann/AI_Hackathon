#!/bin/bash
# OS Agent 提交材料完整性检查脚本
# 生成时间: 2026-04-25

echo "=========================================="
echo "  OS Agent 提交材料完整性检查"
echo "=========================================="
echo ""

# 定义颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_file() {
    if [ -f "$1" ]; then
        size=$(du -h "$1" | cut -f1)
        echo -e "${GREEN}✓${NC} $1 (大小: $size)"
        return 0
    else
        echo -e "${RED}✗${NC} $1 (缺失)"
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        count=$(find "$1" -type f | wc -l)
        echo -e "${GREEN}✓${NC} $1 (文件数: $count)"
        return 0
    else
        echo -e "${RED}✗${NC} $1 (缺失)"
        return 1
    fi
}

# 统计
total=0
pass=0
fail=0

echo "1. 演示视频"
echo "----------------------------------------"
((total++))
check_file "演示视频.mp4" && ((pass++)) || ((fail++))
echo ""

echo "2. 核心文档"
echo "----------------------------------------"
((total++)); check_file "演示文案.md" && ((pass++)) || ((fail++))
((total++)); check_file "提交材料说明文档.md" && ((pass++)) || ((fail++))
((total++)); check_file "提交材料整理指南.md" && ((pass++)) || ((fail++))
((total++)); check_file "题目要求.md" && ((pass++)) || ((fail++))
echo ""

echo "3. 项目根目录"
echo "----------------------------------------"
((total++)); check_file "os-agent/README.md" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/main.py" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/pyproject.toml" && ((pass++)) || ((fail++))
echo ""

echo "4. 源代码目录"
echo "----------------------------------------"
((total++)); check_dir "os-agent/src/agent" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/understanding" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/capabilities" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/guardian" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/connector" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/voice" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/interface" && ((pass++)) || ((fail++))
((total++)); check_dir "os-agent/src/utils" && ((pass++)) || ((fail++))
echo ""

echo "5. 配置文件"
echo "----------------------------------------"
((total++)); check_file "os-agent/configs/app.yaml" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/configs/llm.yaml" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/configs/voice.yaml" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/configs/capabilities.json" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/configs/guardian.json" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/configs/prompts.yaml" && ((pass++)) || ((fail++))
echo ""

echo "6. 设计文档"
echo "----------------------------------------"
((total++)); check_file "os-agent/docs/architecture.md" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/docs/PRD.md" && ((pass++)) || ((fail++))
echo ""

echo "7. 测试材料"
echo "----------------------------------------"
((total++)); check_file "os-agent/测试用例文档.md" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/测试结果报告.md" && ((pass++)) || ((fail++))
echo ""

echo "8. 运行数据"
echo "----------------------------------------"
((total++)); check_file "os-agent/data/logs/app.log" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/data/audit.jsonl" && ((pass++)) || ((fail++))
((total++)); check_file "os-agent/data/learning_memory.md" && ((pass++)) || ((fail++))
echo ""

echo "9. 前端代码"
echo "----------------------------------------"
((total++)); check_dir "os-agent/frontend" && ((pass++)) || ((fail++))
echo ""

echo "=========================================="
echo "  检查结果汇总"
echo "=========================================="
echo -e "总计: ${total} 项"
echo -e "通过: ${GREEN}${pass}${NC} 项"
echo -e "失败: ${RED}${fail}${NC} 项"
echo ""

if [ $fail -eq 0 ]; then
    echo -e "${GREEN}✓ 所有材料完整，可以提交！${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ 存在缺失材料，请补充后重新检查。${NC}"
    exit 1
fi
