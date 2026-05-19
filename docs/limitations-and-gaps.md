# Limitations and Known Gaps

- The frontend is a static SPA served by FastAPI rather than a compiled React build.
- The Azure AI Search adapter is intentionally conservative and focuses on the stable knowledge-base path, not every preview capability.
- The Foundry Agent Service + MCP hop is not wired into the runtime yet.
- Local PDF and Office parsing are limited; production extraction should use Azure parsers.
- Page-range splitting, throughput throttling, and OCR-only-on-selected-pages are scaffolded as architectural seams, not fully automated execution policies.
- Content Understanding output mapping can differ by analyzer design and may require environment-specific tuning.
