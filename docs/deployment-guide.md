# Deployment Guide

## Production Shape

- Host the FastAPI app in Azure Container Apps, App Service, or AKS.
- Replace the JSON job store with a database.
- Move uploaded files and artifacts to Azure Blob Storage.
- Run the ingestion pipeline in a worker process behind a queue.
- Use managed identity for Azure AI Search, Document Intelligence, and Foundry access where available.

## Hardening Tasks

- Add Microsoft Entra sign-in and authorize API routes.
- Add a durable retry queue with poison-message handling.
- Add audit logs and request correlation IDs.
- Add rate limits and file size validation at the edge.
- Add vector embeddings if your retrieval design requires hybrid/vector recall.

## Azure Search Publishing

The current MVP expects admin-key access for simplicity. For production:

- Prefer role-based access and managed identity.
- Restrict index update permissions to the backend workload identity.
- Use a query-only access path for any direct retrieval clients.
