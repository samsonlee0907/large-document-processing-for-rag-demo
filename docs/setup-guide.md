# Setup Guide

## Local Run

1. Create a Python environment.
2. Install dependencies from `requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Start the API and static UI with:

```powershell
uvicorn backend.app:app --reload
```

5. Open `http://127.0.0.1:8000`.

## Recommended Azure Resources

- Azure AI Search with semantic ranker enabled.
- Azure Document Intelligence resource.
- Optional Azure Content Understanding resource plus analyzer.
- Optional Microsoft Foundry project if you plan to extend the app to Foundry Agent Service via MCP.

## Demo Flow

1. Upload `samples/employee-handbook.txt`.
2. Wait for the pipeline to reach `Ready for chat`.
3. Open the Chat screen and ask a policy question.
4. If Azure Search is not configured, the app uses local preview retrieval over the generated chunks.
