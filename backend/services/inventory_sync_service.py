import json
import time
from typing import Any

from backend.clients.thingsboard_client import ThingsBoardApiRestClient
from backend.database import Database


class TelemetryInventorySyncService:
    """
    Servicio que:

    - lee telemetria historica de ThingsBoard y reconstruye el inventario
    - aplica eventos individuales recibidos en tiempo real
    """

    def __init__(self, tb_client: ThingsBoardApiRestClient, database: Database) -> None:
        """
        Recibe sus dos dependencias:
        - el cliente REST de ThingsBoard
        - la capa de MongoDB
        """
        self.tb_client = tb_client
        self.database = database


    @staticmethod
    def parse_value(value: Any) -> Any:
        """
        Interpreta un valor de telemetria de ThingsBoard

        Nunca lanza excepcion: un JSON corrupto se devuelve como string
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return text
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except Exception:
                return value
        return value

    def build_events(self, telemetry: dict) -> list[dict]:
        """
        Reconstruye eventos completos a partir de la telemetria cruda

        Se agrupan por timestamp para recomponer cada evento original y se ordenan cronologicamente.
        """
        grouped: dict[Any, dict] = {}
        for key, entries in telemetry.items():
            for entry in entries:
                ts = entry.get("ts")
                event = grouped.setdefault(ts, {"storedTs": ts})
                event[key] = self.parse_value(entry.get("value"))

        events = list(grouped.values())
        events.sort(key=lambda e: (e.get("eventTs") or "", e.get("storedTs") or 0))
        return events

    @staticmethod
    def rebuild_inventory(events: list[dict]) -> dict:
        """
        Reconstruye el inventario de una nevera reproduciendo su historial
        de eventos en orden
        - cada PRODUCT_ADDED suma stock 
        - cada PRODUCT_REMOVE lo resta (eliminando el item si llega a 0)
        """

        inventory_by_barcode: dict[str, dict] = {}

        # Es interesante saber cuantos eventos hemos tenido que procesar
        processed_inventory_events = 0
        ignored_events = 0
        fridge_id = None

        for event in events:
            fridge_id = fridge_id or event.get("fridgeId")
            event_type = event.get("eventType")
            payload = event.get("eventPayload") or {}

            # Si el evento no aporta a la reconstrucion, continuamos
            if event_type not in {"PRODUCT_ADDED", "PRODUCT_REMOVE"}:
                continue

            barcode = payload.get("barcode")

            qty = Database.to_positive_int(payload.get("cantidad"), 0)
            if not barcode or qty <= 0:
                ignored_events += 1
                continue

            processed_inventory_events += 1
            existing = inventory_by_barcode.get(barcode)

            if event_type == "PRODUCT_ADDED":
                if existing:
                    existing["qty"] += qty
                else:
                    inventory_by_barcode[barcode] = {"barcode": barcode, "qty": qty}
                continue

            if not existing:
                ignored_events += 1
                continue

            existing["qty"] -= qty
            if existing["qty"] <= 0:
                inventory_by_barcode.pop(barcode, None)

        # Ordenamos alfabeticamente para que el inventario sea deterministe independientemente de cuando llegaron los eventos
        items = sorted(inventory_by_barcode.values(), key=lambda i: i["barcode"])
        return {
            "fridgeId": fridge_id,
            "items": items,
            "inventoryEvents": processed_inventory_events,
            "ignoredEvents": ignored_events,
        }

    @staticmethod
    def extract_fridge_id(device_name: str, projection: dict) -> str:
        """
        Decide el fridgeId definitivo del inventario reconstruido
         
        Usara el que venga en la telemetria si existe, o el nombre del dispositivo como fallback
        """
        return projection.get("fridgeId") or device_name

    def sync_tb_device(self, headers: dict, device: dict, start_ts: int = 0, end_ts: int | None = None, limit: int | None = None) -> dict:
        """
        Sincroniza una nevera concreta de principio a fin
        
        Devuelve un resumen con contadores de eventos y el documento guardado.
        """
        device_name = self.tb_client.get_device_name(device)
        tb_device_id = self.tb_client.get_device_id(device, device_name)

        # Si no se pasa end_ts se usa el momento actual en milisegundos
        effective_end_ts = end_ts if end_ts is not None else int(time.time() * 1000)

        telemetry = self.tb_client.get_historical_telemetry(
            headers=headers,
            device_id=tb_device_id,
            start_ts=start_ts,
            end_ts=effective_end_ts,
            limit=limit,
        )
        events = self.build_events(telemetry)
        projection = self.rebuild_inventory(events)
        fridge_id = self.extract_fridge_id(device_name, projection)

        saved_doc = self.database.guardar_inventario_reconstruido(
            fridge_id=fridge_id,
            device_name=device_name,
            items=projection["items"],
        )

        return {
            "fridgeId": fridge_id,
            "deviceName": device_name,
            "tbDeviceId": tb_device_id,
            "totalEvents": len(events),
            "inventoryEvents": projection["inventoryEvents"],
            "ignoredEvents": projection["ignoredEvents"],
            "items": projection["items"],
            "saved": True,
            "savedDoc": {
                "fridgeId": saved_doc["fridgeId"],
                "deviceName": saved_doc["deviceName"],
                "updatedAt": saved_doc["updatedAt"].isoformat(),
            },
        }

    def sync_device_inventory(self, device_name: str, start_ts: int = 0, end_ts: int | None = None, limit: int | None = None) -> dict:
        """
        Sincroniza una nevera buscandola por nombre en ThingsBoard

        Localiza el dispositivo y delega en sync_tb_device.
        """
        headers = self.tb_client.get_auth_headers()
        device = self.tb_client.get_device_by_name(headers, device_name)
        return self.sync_tb_device(headers, device, start_ts=start_ts, end_ts=end_ts, limit=limit)

    def sync_all_devices_inventory(self, start_ts: int = 0, end_ts: int | None = None, limit: int | None = None) -> list[dict]:
        """
        Sincroniza todas las neveras del tenant 

        El fallo de una nevera no aborta el resto
        """
        headers = self.tb_client.get_auth_headers()
        devices = self.tb_client.list_devices(headers)
        results = []

        for device in devices:
            device_name = self.tb_client.get_device_name(device)

            # El fallo de una nevera no aborta el resto
            try:
                results.append({
                    "status": "SYNCED",
                    **self.sync_tb_device(
                        headers, device, start_ts=start_ts, end_ts=end_ts, limit=limit
                    ),
                })
            
            # Lo registramos como ERROR y continuamos
            except Exception as exc:
                results.append({
                    "status": "ERROR",
                    "deviceName": device_name,
                    "detail": str(exc),
                })

        return results

    @staticmethod
    def normalize_individual_event(raw_payload: dict) -> dict:
        """
        Normaliza el JSON recibido desde la Rule Chain de ThingsBoard
        """
        payload = raw_payload

        # Dependiendo del formato la Rule Chain puede devolver msg/payload/data
        for candidate_key in ("msg", "payload", "data"):
            candidate = payload.get(candidate_key)
            if isinstance(candidate, dict) and candidate.get("eventType"):
                payload = candidate
                break

        event_id = payload.get("eventId") or raw_payload.get("eventId")
        fridge_id = payload.get("fridgeId") or raw_payload.get("fridgeId")
        event_type = payload.get("eventType")
        event_payload = payload.get("eventPayload") or raw_payload.get("eventPayload") or {}
        event_ts = payload.get("eventTs")
        device_name = payload.get("deviceName") or raw_payload.get("deviceName") or fridge_id
        tb_device_id = payload.get("tbDeviceId") or raw_payload.get("tbDeviceId")

        if isinstance(event_payload, str):
            try:
                event_payload = json.loads(event_payload)
            except Exception:
                event_payload = {}

        # Debemos tener en cuenta errores
        if not fridge_id:
            raise ValueError("No se ha recibido fridgeId en el evento individual.")
        if not event_type:
            raise ValueError("No se ha recibido eventType en el evento individual.")

        return {
            "eventId": event_id,
            "fridgeId": fridge_id,
            "eventType": event_type,
            "eventPayload": event_payload,
            "eventTs": event_ts,
            "deviceName": device_name or fridge_id,
            "tbDeviceId": tb_device_id,
        }

    def process_individual_event(self, raw_payload: dict) -> dict:
        """
        Camino real 
        
        Recibe el payload crudo que envia la Rule Chain de ThingsBoard, lo normaliza y lo aplica incrementalmente
        sobre el inventario en MongoDB.
        """
        event = self.normalize_individual_event(raw_payload)
        print(
            f"Evento individual recibido: fridgeId={event['fridgeId']} "
            f"eventType={event['eventType']} eventId={event['eventId']}"
        )
        return self.database.aplicar_evento_individual(
            fridge_id=event["fridgeId"],
            device_name=event["deviceName"],
            event_id=event["eventId"],
            event_type=event["eventType"],
            payload=event["eventPayload"],
        )
