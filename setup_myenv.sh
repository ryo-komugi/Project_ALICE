#!/usr/bin/env bash
# ==============================================================================
# Project_ALICE: Virtual Environment Setup Script
# pyenv & Python 3.10 の自動導入から、Docs/requirements_*.txt を源泉とした
# myenv/ 配下の各 venv 自動構築までをワンストップで実行します。
# ==============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
    echo "Error: このスクリプトは Bash 専用です。bash setup_myenv.sh [オプション] で実行してください。" >&2
    exit 2
fi
set -euo pipefail

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
TARGET_PY_VER="3.10.20"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}=== Project_ALICE 開発・本番環境 自動セットアップ ===${NC}"
echo -e "${BLUE}============================================================${NC}"
echo -e "作業ディレクトリ: ${PROJECT_ROOT}"

# 2. pyenv の確認＆自動インストール（PATH は変更せず、絶対パスで実行）
export PYENV_ROOT="$PROJECT_ROOT/.pyenv"
PYENV_BIN="$PYENV_ROOT/bin/pyenv"

if [ ! -x "$PYENV_BIN" ]; then
    if [ -e "$PYENV_ROOT" ]; then
        echo -e "${RED}[ERROR] ${PYENV_ROOT}/bin/pyenv が実行できません。${NC}" >&2
        echo "既存の pyenv を修復するか、PYENV_ROOT を変更してください。" >&2
        exit 1
    fi
    if ! command -v git >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] pyenv のインストールには git が必要です。${NC}" >&2
        exit 1
    fi
    echo -e "${YELLOW}[INFO] pyenv を ${PYENV_ROOT} にインストールします。${NC}"
    git clone https://github.com/pyenv/pyenv.git "$PYENV_ROOT"
    PYENV_BIN="$PYENV_ROOT/bin/pyenv"
fi

echo -e "pyenv バージョン: ${GREEN}$("$PYENV_BIN" --version)${NC}"

# 3. 仮想環境には指定した Python のみを使用し、システム Python へはフォールバックしない。
if ! "$PYENV_BIN" versions --bare | grep -Fxq "$TARGET_PY_VER"; then
    echo -e "${YELLOW}[INFO] Python ${TARGET_PY_VER} をインストールします。${NC}"
    if ! "$PYENV_BIN" install "$TARGET_PY_VER"; then
        echo -e "${RED}[ERROR] Python ${TARGET_PY_VER} のビルドに失敗しました。${NC}" >&2
        echo "Ubuntu/Debian では、build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev が必要です。" >&2
        exit 1
    fi
fi

PYTHON_BIN="$PYENV_ROOT/versions/$TARGET_PY_VER/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo -e "${RED}[ERROR] 指定した Python が見つかりません: ${PYTHON_BIN}${NC}" >&2
    exit 1
fi
PY_VER_STR=$("$PYTHON_BIN" --version 2>&1)
echo -e "仮想環境用 Python: ${GREEN}${PYTHON_BIN}${NC} (${PY_VER_STR})"

# myenv ディレクトリの準備
mkdir -p "$MYENV_DIR"

# 4. 仮想環境の定義（[環境名]="源泉requirementsファイル"）
declare -A ENV_MAP=(
    ["core_env"]="requirements_core_env.txt"
    ["copilot_env"]="requirements_copilot_env.txt"
    ["whisper_env"]="requirements_whisper_env.txt"
    ["pyannote_env"]="requirements_pyannote_env.txt"
)

# 5. 単一環境の構築関数
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

# 6. 引数オプション解析
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

# 7. 実行ループ
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
