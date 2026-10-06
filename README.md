# Louis OS - Autonomous Patch Submission Framework

This document outlines the autonomous tested patch submission, capability recovery, and maintainer loop for Louis OS.

## Overview

Louis OS evolves from internal deliverable creation to lawful, evidence-backed external submission and follow-up.

## Features

- Reject generic drafts that are not repository patches
- Inspect authoritative target issues, repository metadata, and contribution rules
- Build deterministic submission plans with exact required files, tests, and accepted channels
- Reuse existing authorized GitHub identities and tokens
- Handle fork, branch, push, and PR workflows
- Record immutable receipts for all actions
- Monitor CI, reviews, and maintainer comments
- Detect payout requirements and persist missing capabilities
- Pivot to other opportunities when capabilities cannot be acquired autonomously
- Never count revenue until independently verified

## Architecture

### Core Components

1. **Patch Submission Engine** - Handles the full submission lifecycle
2. **Receipt Recorder** - Immutable logging of all actions
3. **CI Monitor** - Tracks build and review status
4. **Capability Manager** - Tracks and recovers missing capabilities
5. **Payout Detector** - Identifies and manages payout requirements

### Workflow

1. Detect or receive a target issue
2. Inspect repository metadata and contribution guidelines
3. Build submission plan
4. Execute patch with testing
5. Submit via PR or direct push
6. Record receipts
7. Monitor for CI/reviews/comments
8. Iterate if needed
9. Verify completion and payout

## Related Issues

- #77: Internal deliverable creation
- #131: Repository metadata inspection
- #137: Submission plan building
- #140: Receipt recording

## License

MIT
