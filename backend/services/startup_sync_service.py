from backend import config
from backend.clients.thingsboard_client import ThingsBoardApiRestClient
from backend.database import Database
from backend.services.inventory_sync_service import TelemetryInventorySyncService


def build_inventory_service() -> TelemetryInventorySyncService:
    """
    Crea las dependencias principales y devuelve el servicio de sincronizacion.
    """

    database = Database()
    tb_client = ThingsBoardApiRestClient()
    return TelemetryInventorySyncService(tb_client=tb_client, database=database)


def run_startup_inventory_rebuild(sync_service: TelemetryInventorySyncService) -> None:
    """
    Reconstruye la foto completa del inventario al arrancar el backend

    A partir de aqui escuchamos las eventos en tiempo real
    """
    
    print("Iniciando sync inicial desde ThingsBoard para todas las neveras del tenant...")

    try:
        results = sync_service.sync_all_devices_inventory(
            start_ts=config.TB_SYNC_START_TS,
            end_ts=None,
            limit=config.TB_QUERY_LIMIT,
        )
        synced = [r for r in results if r.get("status") == "SYNCED"]
        errors = [r for r in results if r.get("status") == "ERROR"]

        print(
            f"Sync inicial completado: "
            f"neveras_sincronizadas={len(synced)} "
            f"neveras_con_error={len(errors)}"
        )
        for item in synced:
            print(
                f"  - {item['deviceName']} -> fridgeId={item['fridgeId']} "
                f"items={len(item['items'])} inventoryEvents={item['inventoryEvents']}"
            )
        for item in errors:
            print(f"  - ERROR {item['deviceName']}: {item['detail']}")

    except Exception as exc:
        print(f"Error en sync inicial ThingsBoard -> MongoDB: {exc}")
