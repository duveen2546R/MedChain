from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .bootstrap import bootstrap_admin
from .config import Settings, settings
from .services.runtime import MedChainRuntime
from .services.artifacts import ArtifactStore
from .store import Repository


def create_app(
    app_settings: Settings = settings,
    repository: Repository | None = None,
    artifact_store: ArtifactStore | None = None,
) -> FastAPI:
    owns_repository = repository is None
    owns_artifact_store = artifact_store is None
    repo = repository or Repository(app_settings)
    runtime = MedChainRuntime(repo, app_settings, artifact_store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.validate(
            require_mongodb=owns_repository,
            require_azure_storage=owns_artifact_store,
        )
        await repo.connect()
        try:
            await runtime.connect()
            await bootstrap_admin(repo, app_settings)
            yield
        finally:
            await runtime.close()
            await repo.close()

    app = FastAPI(title=app_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = app_settings
    app.state.repo = repo
    app.state.runtime = runtime
    app.include_router(router, prefix=app_settings.api_prefix)

    return app


app = create_app()
