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
- `FOUNDRY_CHAT_MODE`
