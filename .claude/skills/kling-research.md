---
name: kling-research
description: Skill for researching Kling AI Motion model — architecture analysis, API exploration, benchmarking, and comparative studies against other video generation models.
trigger: When the user asks about Kling Motion, video generation research, motion synthesis analysis, or wants to run experiments related to Kling AI.
---

# Kling Motion Research Skill

## Purpose

Assist with structured research on Kling AI's motion generation technology, including:

1. **Architecture Analysis** — Investigate Kling's 3D VAE, DiT backbone, and temporal attention mechanisms
2. **API Exploration** — Test and document Kling AI API endpoints for text-to-video and image-to-video
3. **Benchmarking** — Evaluate motion quality metrics (FVD, FID, temporal consistency scores)
4. **Comparative Study** — Compare against Sora, Runway Gen-3, Pika Labs, Stable Video Diffusion

## Workflow

When triggered, follow this research workflow:

### Step 1: Define Research Question
- Clarify what aspect of Kling Motion is being investigated
- Check existing notes in `research/` for prior findings

### Step 2: Gather Information
- Search for latest papers, blog posts, and technical reports on Kling AI
- Review Kling API documentation for relevant endpoints
- Check `references/` for cached sources

### Step 3: Experiment (if applicable)
- Write or modify scripts in `experiments/`
- Store results in `output/`
- Log findings in `research/` with timestamps

### Step 4: Document Findings
- Update research notes with new discoveries
- Add citations to `references/sources.bib` or `references/links.md`
- Summarize key takeaways

## Key Research Areas

### Kling Motion Architecture
- **3D VAE**: Spatiotemporal compression of video data
- **Diffusion Transformer (DiT)**: Core generation backbone with full 3D attention
- **Motion Module**: Temporal consistency and physics-aware motion modeling
- **Multi-modal Conditioning**: Text and image guidance for generation control

### Known Kling Capabilities
- Text-to-video generation (up to 1080p, variable duration)
- Image-to-video animation (single image + motion prompt)
- Motion brush / regional motion control
- Camera motion control (pan, tilt, zoom, orbit)
- Lip sync and face animation
- Video extension and interpolation

### Evaluation Metrics
- **FVD** (Frechet Video Distance) — overall video quality
- **FID** (Frechet Inception Distance) — per-frame quality
- **Temporal Consistency Score** — frame-to-frame coherence
- **Motion Plausibility** — physics and biomechanics adherence
- **Text-Video Alignment** — CLIP-based semantic matching

## References

- Kling AI Platform: https://klingai.com
- Kuaishou Research: https://www.kuaishou.com
- Anthropic Claude API: https://docs.anthropic.com/en/docs
- Anthropic Claude Code: https://docs.anthropic.com/en/docs/claude-code
- Video Diffusion Models Survey: arXiv (search for latest surveys)
- DiT (Diffusion Transformers): Peebles & Xie, 2023
- Stable Video Diffusion: Blattmann et al., 2023

## Output Format

Research findings should be structured as:

```markdown
# [Research Topic]
**Date**: YYYY-MM-DD
**Researcher**: [name]
**Status**: [in-progress | complete | needs-review]

## Question
[What are we investigating?]

## Methodology
[How did we investigate?]

## Findings
[What did we discover?]

## References
[Sources cited]
```
