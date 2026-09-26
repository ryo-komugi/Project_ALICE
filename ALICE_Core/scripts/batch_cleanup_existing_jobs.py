"""
Batch cleanup script for existing jobs in /data/runtime/workspaces
"""
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from hub.workspace import WorkspaceManager
from models.job import JobStatus

initialize_logger()


def main():
    wm = WorkspaceManager(base_dir="/data/runtime/workspaces")
    jobs = wm.list_jobs(limit=500)
    print(f"[*] Found {len(jobs)} total jobs in workspaces.")

    cleaned_count = 0
    skipped_count = 0

    for job in jobs:
        # transcript.json が存在することを確認
        transcript_json = job.workspace_dir / "transcript" / "transcript.json"
        if not transcript_json.exists():
            print(f"[-] [{job.job_id}] Skipped: transcript.json not found.")
            skipped_count += 1
            continue

        result = wm.cleanup_input_audio(job)
        if result:
            print(f"[+] [{job.job_id}] Cleaned audio binary -> placeholder created.")
            cleaned_count += 1
        else:
            skipped_count += 1

    print("\n" + "=" * 50)
    print(f"Batch Cleanup Finished: {cleaned_count} jobs cleaned, {skipped_count} skipped.")
    print("=" * 50)


if __name__ == "__main__":
    main()
