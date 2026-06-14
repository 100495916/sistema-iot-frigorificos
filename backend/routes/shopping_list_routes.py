from fastapi import APIRouter, HTTPException

from backend.database import (
    SHOPPING_LIST_STATUS_COMPLETED,
    SHOPPING_LIST_STATUS_ORDERED,
    SHOPPING_LIST_STATUS_PENDING,
)
from backend.services.inventory_sync_service import TelemetryInventorySyncService


def create_router(sync_service: TelemetryInventorySyncService) -> APIRouter:
    """
    Construye el router de la lista de compra

    Debemos recordar el flujo
    PENDING -> ORDERED -> COMPLETED.
    """
    router = APIRouter()

    @router.get("/api/v2/fridges/{fridge_id}/reglas-lista-compra")
    def listar_reglas_lista_compra(fridge_id: str):
        """
        Devuelve las reglas de reposicion de la nevera, creando las
        reglas por defecto si aun no tiene ninguna
        """
        try:
            return sync_service.database.list_reglas_lista_compra(fridge_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.put("/api/v2/fridges/{fridge_id}/reglas-lista-compra/{barcode}")
    def guardar_regla_lista_compra(fridge_id: str, barcode: str, payload: dict):
        """
        Crea o actualiza la regla de reposicion de un producto mirando si los umbrales son coerentes
        """
        try:
            return sync_service.database.guardar_regla_lista_compra(
                fridge_id=fridge_id,
                barcode=barcode,
                rule_data=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.delete("/api/v2/fridges/{fridge_id}/reglas-lista-compra/{barcode}")
    def eliminar_regla_lista_compra(fridge_id: str, barcode: str):
        """
        Elimina la regla de reposicion de un producto en la nevera
        """
        try:
            return sync_service.database.eliminar_regla_lista_compra(fridge_id, barcode)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))


    @router.get("/api/v2/fridges/{fridge_id}/lista-compra")
    def listar_listas_compra(fridge_id: str, status: str | None = None):
        """
        Devuelve el historial de listas de compra de la nevera, con filtro opcional
        """
        try:
            normalized_status = None
            if status:
                normalized_status = status.upper()

                # Filtros opcionales para ver la lista que nos interesa
                valid = {
                    SHOPPING_LIST_STATUS_PENDING,
                    SHOPPING_LIST_STATUS_COMPLETED,
                    SHOPPING_LIST_STATUS_ORDERED,
                }
                if normalized_status not in valid:
                    raise HTTPException(
                        status_code=400,
                        detail="El estado debe ser PENDING, COMPLETED u ORDERED.",
                    )
            return sync_service.database.list_listas_compra(fridge_id, status=normalized_status)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/v2/fridges/{fridge_id}/lista-compra/pendiente")
    def obtener_lista_compra_pendiente(fridge_id: str):
        """
        Devuelve la lista PENDING actual de la nevera
        """
        try:
            lista = sync_service.database.get_pending_lista_compra(fridge_id)
            if lista is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe lista de compra PENDING para la nevera '{fridge_id}'.",
                )
            return lista
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/v2/fridges/{fridge_id}/lista-compra/{list_id}")
    def obtener_lista_compra(fridge_id: str, list_id: str):
        """
        Devuelve una lista de compra concreta por su listId
        """
        try:
            lista = sync_service.database.get_lista_compra(fridge_id, list_id)
            if lista is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe lista de compra con id '{list_id}'.",
                )
            return lista
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))


    @router.post("/api/v2/fridges/{fridge_id}/lista-compra/evaluar")
    def evaluar_lista_compra(fridge_id: str):
        """
        Reevalua todas las reglas contra el inventario actual y crea o
        actualiza la lista PENDING
        """
        try:
            inventario = sync_service.database.get_inventario(fridge_id)
            if inventario is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe inventario reconstruido para la nevera '{fridge_id}'.",
                )
            return sync_service.database.sincronizar_lista_compra_desde_inventario(
                fridge_id=fridge_id,
                inventory_doc=inventario,
                source="API_MANUAL_EVALUATION",
                allow_create=True,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/api/v2/fridges/{fridge_id}/lista-compra/pendiente/pedir")
    def pedir_online_lista_compra(fridge_id: str):
        """
        Simula el pedido online de la lista PENDING
        Es la transicion PENDING -> ORDERED con fecha de pedido
        """
        try:
            resultado = sync_service.database.pedir_online_lista_compra(fridge_id)
            if resultado is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe lista de compra PENDING para la nevera '{fridge_id}'.",
                )
            return resultado
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/api/v2/fridges/{fridge_id}/lista-compra/pendiente/items")
    def anadir_item_manual(fridge_id: str, payload: dict):
        """
        Añade (o sobreescribe) un item manual en la lista PENDING, creandola
        si no existe
        """
        try:
            barcode = str(payload.get("barcode") or "").strip()
            qty = int(payload.get("qty") or 0)
            if not barcode:
                raise HTTPException(status_code=400, detail="El barcode es obligatorio.")
            if qty <= 0:
                raise HTTPException(status_code=400, detail="La cantidad debe ser mayor que 0.")
            return sync_service.database.anadir_item_manual_lista_compra(fridge_id, barcode, qty)
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/api/v2/fridges/{fridge_id}/lista-compra/{list_id}/completar")
    def completar_lista_compra(fridge_id: str, list_id: str):
        """
        Marca un pedido como recibido
        Es la transicion ORDERED -> COMPLETED

        Se asegura de que no haya estados ilegales
        """
        try:
            lista = sync_service.database.completar_lista_compra(fridge_id, list_id)
            if lista is None:

                # Saldria este error si la lista no esta pedida
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe lista en estado ORDERED con id '{list_id}' para '{fridge_id}'. Solo se puede completar un pedido que ya haya sido cursado online.",
                )
            return lista
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
