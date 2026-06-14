from fastapi import APIRouter, HTTPException

from backend.services.inventory_sync_service import TelemetryInventorySyncService


def create_router(sync_service: TelemetryInventorySyncService) -> APIRouter:
    """
    Construye el router de consulta de inventario (neveras, inventario por
    nevera e historial de eventos)
    """
    router = APIRouter()

    @router.get("/api/v2/fridges")
    def listar_inventarios_reconstruidos():
        """
        Devuelve el inventario de todas las neveras conocidas
        """
        try:
            return sync_service.database.list_inventarios()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/v2/fridges/{fridge_id}/inventario")
    def obtener_inventario_reconstruido(fridge_id: str):
        """
        Devuelve la foto actual del inventario de una nevera
        """
        try:
            inventario = sync_service.database.get_inventario(fridge_id)
            if inventario is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe inventario reconstruido para la nevera '{fridge_id}'.",
                )
            return inventario
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/v2/fridges/{fridge_id}/eventos-procesados")
    def listar_eventos_procesados(fridge_id: str, limit: int = 50):
        """
        Devuelve el historial de eventos aplicados a una nevera con un limite
        """
        try:
            return sync_service.database.list_eventos_procesados(fridge_id, limit=limit)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
