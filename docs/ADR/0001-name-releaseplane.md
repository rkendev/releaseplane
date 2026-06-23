# ADR 0001: Project name is ReleasePlane

Date: 2026-06-23
Status: Accepted

## Context

The original project spec called this build "PromptOps Control Plane." A private repo (`PromptOps Build Progress`, v0.1.0 code-complete 2026-06-08) already exists under that name. The Naming Hygiene rule of the council process flags collisions that would confuse a recruiter scanning the portfolio.

## Decision

Use the name **ReleasePlane**.

Repo slug: `releaseplane`. Demo URL placeholder: `releaseplane.<vps-domain>`.

## Rationale

The release lifecycle (draft / candidate / active / rolled-back) is the pillar of the system; the name centers that pillar. It is domain-neutral, reads as platform engineering, and has no overlap with prior portfolio entries.

## Alternatives considered

- **PromptOps Control Plane** (the spec name). Rejected: collides with the existing private repo on the same name.
- **InvoiceGate**. Rejected: undersells the four-plane scope; reads as a narrow extraction tool, not a platform.
- **GovernedLLM**. Rejected: vaguer than ReleasePlane and weaker concrete demo hook than InvoiceGate.

## Consequences

- All public-facing surfaces (README, repo, demo URL, Medium post if any) use ReleasePlane.
- No reference to the spec name "PromptOps Control Plane" appears in public surfaces.
- The existing private PromptOps repo remains private; no rename needed.
