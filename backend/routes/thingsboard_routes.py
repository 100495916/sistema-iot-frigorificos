from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.services.inventory_sync_service import TelemetryInventorySyncService

# Alertas activas en memoria
_alertas_activas: dict[str, dict] = {}


def _extraer_fridge_id(payload: dict) -> str:
    """
    Saca el identificador de nevera del payload de la Rule Chain
    """
    return (payload.get("fridgeId")
        or payload.get("originatorName")
        or payload.get("deviceName")
        or "desconocida"
    )


def create_router(sync_service: TelemetryInventorySyncService) -> APIRouter:
    """
    Construye el router de integracion con ThingsBoard en tiempo real
    """
    router = APIRouter()

    @router.post("/api/v2/thingsboard/individual")
    def procesar_evento_individual(payload: dict):
        """
        Webhook que la Rule Chain invoca con cada evento de telemetria

        Aplica el evento sobre el inventario en MongoDB y devuelve el
        resultado
        """
        try:
            return sync_service.process_individual_event(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            print(f"Error procesando evento individual de ThingsBoard: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/api/v2/thingsboard/alarma")
    def procesar_alarma(payload: dict):
        """
        Webhook invocado por la Rule Chain al crearse la alarma

        Registra la alerta en el dict en memoria que consulta el dashboard.
        """

        # Print para debuggear
        fridge_id = _extraer_fridge_id(payload)
        print(f"Alarma recibida: PUERTA_ABIERTA — nevera {fridge_id}")

        _alertas_activas[fridge_id] = {
            "fridgeId": fridge_id,
            "mensaje": f"Puerta abierta mas de 30 segundos",
            "desde": datetime.now(timezone.utc).isoformat(),
        }

        return {"ok": True, "fridgeId": fridge_id}

    @router.post("/api/v2/thingsboard/alarma/clear")
    def limpiar_alarma(payload: dict):
        """
        Webhook invocado por la Rule Chain cuando la alarma se limpia

        Elimina la alerta de la nevera del dict en
        memoria, ahciendo que el banner desaparezca en el dashboard
        """
        fridge_id = _extraer_fridge_id(payload)
        eliminada = _alertas_activas.pop(fridge_id, None)

        # Print para debuggear
        print(f"Alarma {'limpiada' if eliminada else 'no encontrada'}: nevera {fridge_id}")
        return {"ok": True, "fridgeId": fridge_id}

    @router.get("/api/v2/alertas/activas")
    def obtener_alertas_activas():
        """
        Devuelve las alertas de puerta abierta actualmente activas

        El dashboard lo consulta cada 20 segundos
        """
        return list(_alertas_activas.values())

    return router
