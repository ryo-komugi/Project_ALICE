# ==========================================
# Core Module Runners Definition (Registry & Artifact Contract)
# ==========================================
MODULE_RUNNERS = {
    "transcript": {
        "python_bin": "/home/takuya/Project_ALICE/myenv/whisper_env/bin/python",
        "cli_path": "/home/takuya/Project_ALICE/ALICE_Transcript/cli.py",
        "module_cwd": "/home/takuya/Project_ALICE/ALICE_Transcript",
        "artifact_dir": "transcript",
        "primary_artifact": "transcript.txt",
        "contract_artifacts": ["transcript.json", "transcript.txt", "metadata.json"],
    },
    "summary": {
        "python_bin": "/home/takuya/Project_ALICE/myenv/core_env/bin/python",
        "cli_path": "/home/takuya/Project_ALICE/ALICE_Summary/cli.py",
        "module_cwd": "/home/takuya/Project_ALICE/ALICE_Summary",
        "artifact_dir": "summary",
        "primary_artifact": "summary.txt",
        "contract_artifacts": ["summary.md", "summary.txt", "analysis.json", "metadata.json"],
    },
    "minutes": {
        "python_bin": "/home/takuya/Project_ALICE/myenv/core_env/bin/python",
        "cli_path": "/home/takuya/Project_ALICE/ALICE_Minutes/cli.py",
        "module_cwd": "/home/takuya/Project_ALICE/ALICE_Minutes",
        "artifact_dir": "minutes",
        "primary_artifact": "minutes.md",
        "contract_artifacts": ["minutes.txt", "minutes.md", "analysis.json", "metadata.json"],
    },
}
