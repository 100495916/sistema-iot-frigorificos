import uuid
from datetime import datetime, timezone


class EventType:
    """
    Catalogo de tipos de evento que el edge puede emitir hacia ThingsBoard
    """
    PRODUCT_ADDED = "PRODUCT_ADDED"
    PRODUCT_REMOVE = "PRODUCT_REMOVE"
    DOOR_OPEN = "DOOR_OPEN"
    DOOR_CLOSE = "DOOR_CLOSE"
    FRIDGE_CREATED = "FRIDGE_CREATED"


class EventStatus:
    """
    Estados posibles de un evento dentro del buffer local
    """
    PENDING = "PENDING"
    SENT = "SENT"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class Event:
    def __init__(self, fridge_id, event_type, payload=None, event_id=None):
        """
        Crea un evento con identificador unico,
        timestamp UTC actual y estado inicial PENDING
        """
        self.event_id = event_id if event_id else uuid.uuid4().hex
        self.fridge_id = fridge_id
        self.type = event_type

        # El payload sera vacio para eventos que no necesitan datos extra.
        self.payload = payload if payload else {}
        self.ts = datetime.now(timezone.utc).isoformat()
        self.status = EventStatus.PENDING
        self.retry_count = 0
        self._validar()

    def _validar(self):
        """
        Valida que el evento tenga una estructura coherente
        """
        if self.type in [EventType.DOOR_OPEN, EventType.DOOR_CLOSE, EventType.FRIDGE_CREATED]:
            self.payload = {}
        elif self.type in [EventType.PRODUCT_ADDED, EventType.PRODUCT_REMOVE]:
            if "barcode" not in self.payload or "cantidad" not in self.payload:
                raise ValueError(f"Faltan datos para el evento {self.type}")


    def to_dict(self):
        """
        Serializa el evento a un dict plano para guardarlo como linea
        en el buffer local
        """
        return {
            "eventId": self.event_id,
            "fridgeId": self.fridge_id,
            "type": self.type,
            "payload": self.payload,
            "ts": self.ts,
            "status": self.status,
            "retry_count": self.retry_count,
        }

    @staticmethod
    def from_dict(datos):
        """
        Reconstruye un Event desde el dict leido del buffer JSON
        """
        evento = Event(datos["fridgeId"], datos["type"], datos["payload"], event_id=datos.get("eventId"))
        evento.ts = datos["ts"]
        evento.status = datos.get("status", EventStatus.PENDING)
        evento.retry_count = datos.get("retry_count", 0)
        return evento

    def mark_completed(self):
        """Marca el evento como confirmado por el broker"""
        self.status = EventStatus.COMPLETED

    def mark_error(self):
        """Marca el evento como fallido de forma definitiva"""
        self.status = EventStatus.ERROR
