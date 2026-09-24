# ALICE_Core AGENTS

## Overview

ALICE_Core is the orchestrator of Project_ALICE.

It does not implement speech recognition,
speaker diarization,
or summarization.

Those responsibilities belong to each module.

## Development Policy

Always read README.md before making decisions.

Respect module boundaries.

Do not move responsibilities from modules into Core.

Discuss architecture before implementation.

When requirements are ambiguous,
ask the user instead of assuming.

Large architectural changes require explicit approval.

Prefer small commits.

Do not change public interfaces without discussion.

## Coding Style

Follow the existing coding style.

Keep functions small.

Add comments only when they improve understanding.

Avoid unnecessary dependencies.

## Goal

Prioritize maintainability and clear responsibilities over short-term convenience.
