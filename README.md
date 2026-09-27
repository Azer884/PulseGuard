# PulseGuard — Privacy-First AI Workforce & Project Alignment

PulseGuard is a privacy-first AI workforce assistant designed to identify project friction, improve employee-project alignment, and reduce onboarding time when employees transition between projects.

## Privacy and Data Handling

PulseGuard processes employee activity and contextual signals locally on the employee's device whenever possible.

- Raw telemetry remains on-device
- Camera data remains on-device
- Keystrokes remain on-device
- Screenshots remain on-device
- Detailed activity logs remain on-device

Only a minimal project-friction score and high-level insights are shared with authorized management.

## Core Features

- Local-first employee activity and context analysis
- Privacy-preserving project friction scoring
- Employee/project skill and context matching
- Potential cross-project alignment recommendations
- Human approval for project transitions
- AI-generated project onboarding briefs
- GitHub repository, issue, PR, and documentation analysis
- Manager dashboard with aggregated insights
- Transparent AI reasoning and recommendations
- Synthetic/demo data for the hackathon prototype

## AI & Infrastructure

PulseGuard can use NVIDIA Brev for GPU-accelerated AI workloads such as local model inference, embeddings, document analysis, and semantic project matching.

Claude Code is used to accelerate development of the frontend, backend, AI pipeline, integrations, testing, and deployment.

The system is designed around a local-first architecture so sensitive employee information can be processed on-device while only necessary high-level results are transmitted.

## Core Workflow

Employee device → Local analysis → Project friction score → Project compatibility analysis → Human-approved project transition → AI-generated onboarding context

## Transition and Onboarding Flow

When persistent project friction is detected, PulseGuard analyzes employee skills, preferences, workload, and available projects to identify potential project alignments.

Any project transition requires human approval and is never automatically imposed on the employee.

Once a transition is approved, PulseGuard analyzes the destination project's documentation, GitHub issues, pull requests, tasks, and recent development context to generate a personalized onboarding brief.

## Safety and Scope

PulseGuard is not intended to diagnose medical or psychological conditions or make automated employment decisions.

Its purpose is to provide privacy-conscious insights into project/workflow friction and support informed human decision-making around project alignment.
