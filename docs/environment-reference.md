# Environment Reference

## Core

- `APP_NAME`: UI and API display name.
- `APP_ENV`: environment label.
- `LOG_LEVEL`: structured log verbosity.

## Chunking

- `CHUNK_SIZE_TOKENS`: target chunk size for structure-aware chunking.
- `CHUNK_OVERLAP_TOKENS`: overlap between adjacent chunks.
- `MAX_PAGES_PER_SEGMENT`: intended upper bound for a parser segment.
- `LARGE_DOCUMENT_PAGE_THRESHOLD`: threshold that marks a document as large.
- `HARD_PAGE_SPLIT_THRESHOLD`: threshold that should force document segmentation.
- `HARD_FILE_SPLIT_THRESHOLD_MB`: file-size threshold that should also force PDF segmentation.
- `ENABLE_LLM_BOUNDARY_STITCHING`: enables GPT-assisted seam repair for ambiguous cross-segment paragraph boundaries when a Foundry chat deployment is configured.

## Parser Adapters

- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `AZURE_DOCUMENT_INTELLIGENCE_MODEL`
- `AZURE_CONTENT_UNDERSTANDING_ENDPOINT`
- `AZURE_CONTENT_UNDERSTANDING_KEY`
- `AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID`

## Search / Foundry IQ Path

- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_SEARCH_QUERY_KEY`
- `AZURE_SEARCH_INDEX_NAME`
- `AZURE_SEARCH_KNOWLEDGE_SOURCE_NAME`
- `AZURE_SEARCH_KNOWLEDGE_BASE_NAME`
- `AZURE_SEARCH_API_VERSION`
- `AZURE_SEARCH_EXTRA_SOURCES_JSON`: optional JSON array of extra search-index knowledge sources to include in the knowledge base for multi-index routing.
- `AZURE_SEARCH_AUTO_BROADCAST_LIMIT`: when no source-specific hint matches, auto mode can broadcast across all configured indexes up to this limit.
- `FOUNDRY_CHAT_MODE`

## Figure Artifacts

- `ENABLE_IMAGE_UNDERSTANDING`: enables GPT-based figure descriptions when a Foundry chat deployment is configured.
- `MAX_FIGURE_IMAGE_PIXELS`: upper bound used when normalizing extracted PDF figures before optional image understanding.
- `MAX_FIGURE_IMAGE_DIMENSION`: maximum width or height used when downscaling extracted PDF figures before optional image understanding.

Large embedded PDF figures are normalized to retrieval-safe PNG artifacts. Oversized figures are downscaled before GPT-based image understanding so a single large TIFF does not fail the whole ingestion job.
