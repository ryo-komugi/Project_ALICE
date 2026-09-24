#!/usr/bin/env bash
# ==============================================================================
# Project_ALICE: Virtual Environment Setup Script
# Docs/requirements_*.txt を源泉として myenv/ 配下に各 venv を自動構築します。
# ==============================================================================
set -e

# 色設定（視認性向上）
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. プロジェクトルートディレクトリの自動特定
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
MYENV_DIR="$PROJECT_ROOT/myenv"
DOCS_DIR="$PROJECT_ROOT/Docs"

echo -e "${BLUE}=== Project_ALICE 仮想環境（venv）自動セットアップ ===${NC}"
echo -e "作業ディレクトリ: ${PROJECT_ROOT}"

# 2. Python 3.10 インタプリタの自動検出（PyTorch等の互換性確保）
PYTHON_BIN=""
if [ -x "$HOME/.pyenv/versions/3.10.20/bin/python" ]; then
    PYTHON_BIN="$HOME/.pyenv/versions/3.10.20/bin/python"
elif command -v pyenv &>/dev/null && pyenv which python3.10 &>/dev/null; then
    PYTHON_BIN="$(pyenv which python3.10)"
elif command -v python3.10 &>/dev/null; then
    PYTHON_BIN="$(command -v python3.10)"
else
    PYTHON_BIN="python3"
fi

PY_VER=$("$PYTHON_BIN" --version 2>&1)
echo -e "使用 Python: ${GREEN}${PYTHON_BIN}${NC} (${PY_VER})"

# myenv ディレクトリの準備
mkdir -p "$MYENV_DIR"

# 3. 仮想環境の定義（[環境名]="源泉requirementsファイル"）
declare -A ENV_MAP=(
    ["core_env"]="requirements_core_env.txt"
    ["copilot_env"]="requirements_copilot_env.txt"
    ["whisper_env"]="requirements_whisper_env.txt"
    ["pyannote_env"]="requirements_pyannote_env.txt"
)

# 4. 単一環境の構築関数
setup_single_env() {
    local env_name="$1"
    local req_file="$2"
    local target_dir="$MYENV_DIR/$env_name"
    local req_path="$DOCS_DIR/$req_file"

    echo ""
    echo -e "${BLUE}------------------------------------------------------------${NC}"
    echo -e "▶ セットアップ開始: ${YELLOW}${env_name}${NC}"
    echo -e "  源泉ファイル: ${req_path}"
    echo -e "${BLUE}------------------------------------------------------------${NC}"

    if [ ! -f "$req_path" ]; then
        echo -e "${RED}[ERROR] 源泉ファイルが見つかりません: ${req_path}${NC}"
        return 1
    fi

    # 既存環境の存在確認
    if [ -d "$target_dir" ]; then
        if [ "$CLEAN_MODE" = "true" ]; then
            echo -e "${YELLOW}[WARN] 既存の ${env_name} を削除して再構築します...${NC}"
            rm -rf "$target_dir"
        else
            echo -e "${GREEN}[SKIP] ${env_name} は既に存在します。（再作成する場合は --clean を指定）${NC}"
            return 0
        fi
    fi

    # venv の作成
    echo -e "[1/3] 仮想環境を作成中..."
    "$PYTHON_BIN" -m venv "$target_dir"

    # pip の最新化
    echo -e "[2/3] pip をアップグレード中..."
    "$target_dir/bin/pip" install --upgrade pip -q

    # PyTorch CUDA wheel extra-index-url の自動判定
    EXTRA_INDEX=""
    if grep -q "+cu" "$req_path" 2>/dev/null; then
        echo -e "[INFO] PyTorch CUDA ホイールを検出しました。PyTorch index URL を付与します。"
        EXTRA_INDEX="--extra-index-url https://download.pytorch.org/whl/cu128"
    fi

    # requirements の一括インストール
    echo -e "[3/3] パッケージを一括インストール中 (しばらくお待ちください)..."
    if [ -n "$EXTRA_INDEX" ]; then
        "$target_dir/bin/pip" install -r "$req_path" $EXTRA_INDEX -q
    else
        "$target_dir/bin/pip" install -r "$req_path" -q
    fi

    echo -e "${GREEN}✔ ${env_name} の構築が正常に完了しました！${NC}"
}

# 5. 引数オプション解析
CLEAN_MODE="false"
TARGET_ARG=""

for arg in "$@"; do
    case "$arg" in
        --clean|--force)
            CLEAN_MODE="true"
            ;;
        core|core_env)
            TARGET_ARG="core_env"
            ;;
        copilot|copilot_env)
            TARGET_ARG="copilot_env"
            ;;
        whisper|whisper_env)
            TARGET_ARG="whisper_env"
            ;;
        pyannote|pyannote_env)
            TARGET_ARG="pyannote_env"
            ;;
        --help|-h)
            echo "使い方: ./setup_myenv.sh [オプション] [対象環境]"
            echo "オプション:"
            echo "  --clean, --force   既存環境を削除してクリーンインストール"
            echo "対象環境 (省略時は全環境を一括構築):"
            echo "  core, copilot, whisper, pyannote"
            exit 0
            ;;
    esac
done

# 6. 実行ループ
if [ -n "$TARGET_ARG" ]; then
    setup_single_env "$TARGET_ARG" "${ENV_MAP[$TARGET_ARG]}"
else
    # 全環境を順番に構築
    for env in core_env copilot_env whisper_env pyannote_env; do
        setup_single_env "$env" "${ENV_MAP[$env]}"
    done
fi

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}🎉 すべての仮想環境セットアップ処理が完了しました！${NC}"
echo -e "${GREEN}============================================================${NC}"
