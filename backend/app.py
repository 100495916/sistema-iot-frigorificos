from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.routes import inventory_routes, shopping_list_routes, thingsboard_routes
from backend.services.startup_sync_service import (
    build_inventory_service,
    run_startup_inventory_rebuild,
)


def create_app() -> FastAPI:
    """
    Fabrica de la aplicacion del backend 
    
    Construye las dependencias, programa la reconstruccion del inventario en el
    arranque, configura CORS y registra los tres routers de la API.
    """
    sync_service = build_inventory_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Antes de aceptar trafico, reconstruye el inventario de todas las neveras
        """
        run_startup_inventory_rebuild(sync_service)
        yield

    app = FastAPI(title="API del Frigorifico IoT", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.BACKEND_CORS_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        """
        Health check
        
        Si la base de datos no responde, devolvemos 503
        """
        try:
            sync_service.database.client.admin.command("ping")
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"MongoDB no responde: {exc}",
            )
        return {"status": "ok", "mongo": "up"}

    # Registramos los tres routers de la API.
    app.include_router(inventory_routes.create_router(sync_service))
    app.include_router(shopping_list_routes.create_router(sync_service))
    app.include_router(thingsboard_routes.create_router(sync_service))

    return app
