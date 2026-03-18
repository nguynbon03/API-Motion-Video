# ReSearch Kling Motion

## Project Overview

This project is a research initiative focused on **Kling AI Motion** — a video generation and motion synthesis model developed by **Kuaishou Technology**. The goal is to study, document, and experiment with Kling's motion generation capabilities, including text-to-video, image-to-video, and motion transfer pipelines.

## Research Scope

- **Kling Motion Model Architecture**: Investigating the underlying 3D VAE, diffusion transformer (DiT), and temporal modeling components.
- **Motion Generation Quality**: Benchmarking motion coherence, physics plausibility, and temporal consistency.
- **API & Integration**: Exploring Kling AI's public API endpoints for programmatic video generation.
- **Comparative Analysis**: Comparing Kling Motion against other state-of-the-art models (Sora, Runway Gen-3, Pika, Stable Video Diffusion).

## Key References

- Kling AI Official: https://klingai.com
- Kuaishou Technology: https://www.kuaishou.com
- Kling API Documentation: https://docs.klingai.com (if available)
- Research papers on video diffusion models and 3D-aware generation

## Conventions

- All research notes go in `research/` directory
- Experiment scripts go in `experiments/` directory
- Skills/tools go in `.claude/skills/` directory
- Use English for code and comments; Vietnamese or English for research notes
- Reference all external sources with proper citations

## Commands

- `python experiments/run_benchmark.py` — Run motion quality benchmarks
- `python experiments/api_test.py` — Test Kling API connectivity

## Important Notes

- Respect Kling AI's Terms of Service and rate limits when using their API
- Do not store API keys in the repository — use environment variables
- All generated media should be stored in `output/` (gitignored)
