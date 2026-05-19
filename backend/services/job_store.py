from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Callable

from backend.core.config import settings
from backend.domain.models import JobRecord, JobStatus, JobStoreModel, PipelineMessage, PublishStatus, Stage


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        if not self.path.exists():
            self._write(JobStoreModel())

    def _read(self) -> JobStoreModel:
        with self.path.open("r", encoding="utf-8") as handle:
            return JobStoreModel.model_validate(json.load(handle))

    def _write(self, model: JobStoreModel) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(model.model_dump(mode="json"), handle, indent=2)

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            return self._read().jobs

    def get(self, doc_id: str) -> JobRecord:
        with self._lock:
            store = self._read()
            for job in store.jobs:
                if job.doc_id == doc_id:
                    return job
        raise KeyError(doc_id)

    def upsert(self, record: JobRecord) -> JobRecord:
        with self._lock:
            store = self._read()
            replaced = False
            jobs: list[JobRecord] = []
            for current in store.jobs:
                if current.doc_id == record.doc_id:
                    jobs.append(record)
                    replaced = True
                else:
                    jobs.append(current)
            if not replaced:
                jobs.append(record)
            self._write(JobStoreModel(jobs=jobs))
        return record

    def delete(self, doc_id: str) -> None:
        with self._lock:
            store = self._read()
            store.jobs = [job for job in store.jobs if job.doc_id != doc_id]
            self._write(store)

    def mutate(self, doc_id: str, mutator: Callable[[JobRecord], None]) -> JobRecord:
        with self._lock:
            store = self._read()
            for idx, job in enumerate(store.jobs):
                if job.doc_id == doc_id:
                    mutator(job)
                    job.touch()
                    store.jobs[idx] = job
                    self._write(store)
                    return job
        raise KeyError(doc_id)

    def append_activity(self, doc_id: str, message: str, level: str = "info") -> JobRecord:
        def mutate(job: JobRecord) -> None:
            job.activity.append(PipelineMessage(level=level, message=message))

        return self.mutate(doc_id, mutate)

    def mark_stage(
        self,
        doc_id: str,
        stage: Stage,
        progress: int,
        message: str,
        parser_path: str | None = None,
    ) -> JobRecord:
        def mutate(job: JobRecord) -> None:
            job.stage = stage
            job.progress = progress
            if parser_path:
                job.parser_path = parser_path
            job.activity.append(PipelineMessage(message=message))
            if stage == Stage.failed:
                job.status = JobStatus.failed
            elif stage == Stage.ready:
                job.status = JobStatus.ready
            else:
                job.status = JobStatus.processing

        return self.mutate(doc_id, mutate)

    def update_publish_status(self, doc_id: str, publish_status: PublishStatus) -> JobRecord:
        def mutate(job: JobRecord) -> None:
            job.publish_status = publish_status

        return self.mutate(doc_id, mutate)


job_store = JobStore(settings.store_path)
