#!/usr/bin/env bash
# Usage: ./start_alice_core.sh [--ip IP] [--port PORT]
#   Options are optional and can be specified in either order. Defaults are
#   ALICE_CORE_HOST/ALICE_CORE_PORT, then 127.0.0.1/8000. Options take precedence.
# Examples:
#   ./start_alice_core.sh
#   ./start_alice_core.sh --ip 127.0.0.1 --port 8001
#   ./start_alice_core.sh --port 8001 --ip 0.0.0.0
# Either option can be used alone.
set -Eeuo pipefail

# Production entry point for ALICE_Core. Run as the intended service user;
# this script deliberately does not use sudo or change process credentials.
PROJECT_ROOT_FROM_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CORE_DIR="${PROJECT_ROOT_FROM_SCRIPT}/ALICE_Core"
PYTHON_BIN="${PROJECT_ROOT_FROM_SCRIPT}/myenv/core_env/bin/python"
ENV_FILE="${CORE_DIR}/.env"
CORE_HOST="${ALICE_CORE_HOST:-127.0.0.1}"
CORE_PORT="${ALICE_CORE_PORT:-8000}"
CORE_SSL_KEYFILE="${ALICE_CORE_SSL_KEYFILE:-}"
CORE_SSL_CERTFILE="${ALICE_CORE_SSL_CERTFILE:-}"

while (( $# )); do
  case "$1" in
    --ip)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then
        echo "Missing value for --ip" >&2
        echo "Usage: $0 [--ip IP] [--port PORT] [--ssl-keyfile PATH --ssl-certfile PATH]" >&2
        exit 2
      fi
      CORE_HOST="$2"
      shift 2
      ;;
    --port)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then
        echo "Missing value for --port" >&2
        echo "Usage: $0 [--ip IP] [--port PORT] [--ssl-keyfile PATH --ssl-certfile PATH]" >&2
        exit 2
      fi
      CORE_PORT="$2"
      shift 2
      ;;
    --ssl-keyfile)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then
        echo "Missing value for --ssl-keyfile" >&2
        echo "Usage: $0 [--ip IP] [--port PORT] [--ssl-keyfile PATH --ssl-certfile PATH]" >&2
        exit 2
      fi
      CORE_SSL_KEYFILE="$2"
      shift 2
      ;;
    --ssl-certfile)
      if (( $# < 2 )) || [[ -z "$2" || "$2" == --* ]]; then
        echo "Missing value for --ssl-certfile" >&2
        echo "Usage: $0 [--ip IP] [--port PORT] [--ssl-keyfile PATH --ssl-certfile PATH]" >&2
        exit 2
      fi
      CORE_SSL_CERTFILE="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--ip IP] [--port PORT] [--ssl-keyfile PATH --ssl-certfile PATH]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--ip IP] [--port PORT] [--ssl-keyfile PATH --ssl-certfile PATH]" >&2
      exit 2
      ;;
  esac
done

if [[ -n "${CORE_SSL_KEYFILE}" || -n "${CORE_SSL_CERTFILE}" ]]; then
  if [[ -z "${CORE_SSL_KEYFILE}" || -z "${CORE_SSL_CERTFILE}" ]]; then
    echo "Both --ssl-keyfile and --ssl-certfile are required for direct HTTPS" >&2
    exit 2
  fi
  if [[ "${CORE_SSL_KEYFILE}" != /* || "${CORE_SSL_CERTFILE}" != /* ]]; then
    echo "TLS key and certificate paths must be absolute" >&2
    exit 2
  fi
  if [[ ! -r "${CORE_SSL_KEYFILE}" || ! -r "${CORE_SSL_CERTFILE}" ]]; then
    echo "TLS key or certificate is not readable" >&2
    exit 1
  fi
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ALICE Core Python environment not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -r "${ENV_FILE}" ]]; then
  echo "ALICE Core environment file is missing or unreadable: ${ENV_FILE}" >&2
  exit 1
fi

if [[ ! "${CORE_PORT}" =~ ^[0-9]{1,5}$ ]]; then
  echo "Invalid port: ${CORE_PORT} (expected 1-65535)" >&2
  exit 2
fi
CORE_PORT_NUMBER=$((10#${CORE_PORT}))
if (( CORE_PORT_NUMBER < 1 || CORE_PORT_NUMBER > 65535 )); then
  echo "Invalid port: ${CORE_PORT} (expected 1-65535)" >&2
  exit 2
fi
CORE_PORT="${CORE_PORT_NUMBER}"

export PROJECT_ROOT="${PROJECT_ROOT:-${PROJECT_ROOT_FROM_SCRIPT}}"
cd "${CORE_DIR}"

# Check the GPU lock before accepting jobs. Keep the lock file in place; the
# application uses flock and does not remove the file after each operation.
"${PYTHON_BIN}" - "${ENV_FILE}" <<'PY'
import os
import sys
from pathlib import Path
from dotenv import dotenv_values

env_file = Path(sys.argv[1])
env_values = dotenv_values(env_file)
lock_name = os.environ.get("ALICE_GPU_LOCK_FILE")
if lock_name is None:
    lock_name = env_values.get("ALICE_GPU_LOCK_FILE")
if lock_name is None:
    lock_name = "/tmp/alice_gpu.lock"
lock_path = Path(lock_name).expanduser()
if not lock_path.is_absolute():
    lock_path = Path.cwd() / lock_path

try:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o666)
        os.fchmod(fd, 0o666)
    except FileExistsError:
        fd = os.open(str(lock_path), os.O_RDWR)
    lock_stat = os.fstat(fd)
    os.close(fd)
except OSError as exc:
    print(
        f"Cannot access GPU lock file {lock_path}: {exc} "
        f"(uid={os.geteuid()}, gid={os.getegid()}, groups={os.getgroups()})",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(
    f"GPU lock file accessible: {lock_path} "
    f"(process={os.geteuid()}:{os.getegid()}, "
    f"file={lock_stat.st_uid}:{lock_stat.st_gid}, mode={oct(lock_stat.st_mode & 0o777)})",
    flush=True,
)
PY

echo "Starting ALICE_Core as $(id -un) (uid=$(id -u), gid=$(id -g)) at ${CORE_HOST}:${CORE_PORT}"

UVICORN_SSL_ARGS=()
if [[ -n "${CORE_SSL_KEYFILE}" ]]; then
  UVICORN_SSL_ARGS+=(--ssl-keyfile "${CORE_SSL_KEYFILE}" --ssl-certfile "${CORE_SSL_CERTFILE}")
fi

exec "${PYTHON_BIN}" -m uvicorn main:app \
  --host "${CORE_HOST}" \
  --port "${CORE_PORT}" \
  --proxy-headers \
  --forwarded-allow-ips "${ALICE_CORE_TRUSTED_PROXY_IPS:-127.0.0.1}" \
  "${UVICORN_SSL_ARGS[@]}"
