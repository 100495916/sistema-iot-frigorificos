import uuid
from datetime import datetime, timezone

import requests
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from backend import config


SHOPPING_LIST_STATUS_PENDING = "PENDING"
SHOPPING_LIST_STATUS_COMPLETED = "COMPLETED"
SHOPPING_LIST_STATUS_ORDERED = "ORDERED"

# Listas por defecto para pruebas
DEFAULT_SHOPPING_RULES = [
    {
        "barcode": "8410128010096",
        "productName": "Leche entera Pascual",
        "minQty": 1,
        "targetQty": 3,
        "enabled": True,
    },
    {
        "barcode": "8437015354019",
        "productName": "Huevos Camperos",
        "minQty": 2,
        "targetQty": 6,
        "enabled": True,
    },
    {
        "barcode": "5449000133328",
        "productName": "Cocacola Zero",
        "minQty": 1,
        "targetQty": 9,
        "enabled": False,
    },
    {
        "barcode": "FRESH_PLATANO",
        "productName": "Platano",
        "minQty": 6,
        "targetQty": 10,
        "enabled": True,
    }
]


class Database:
    """
    Capa de acceso a MongoDB del backend.
    """

    def __init__(self):
        """
        Conecta a MongoDB Atlas usando la URI del .env

        Se asegura que las coleccions e indices queden creados
        """
        if not config.MONGODB_URI:
            raise ValueError("MONGODB_URI no esta configurada en backend/.env")

        self.MONGODB_URI = config.MONGODB_URI
        self.DB_NAME = config.DB_NAME

        self.client = MongoClient(self.MONGODB_URI)
        self.db = self.client[self.DB_NAME]

        print(f"Conectado a MongoDB Atlas ({self.DB_NAME})")

        self.inventario = self.db["inventario"]

        self.eventos_procesados = self.db["eventos_procesados"]

        self.productos_cache = self.db["productos_cache"]

        self.reglas_lista_compra = self.db["reglas_lista_compra"]

        self.lista_compra = self.db["lista_compra"]
        self.ensure_indexes()

    def ensure_indexes(self):
        """
        Crea los indices de las colecciones que definen las claves del dominio: 
        - un inventario por fridgeId
        - un eventId procesado una sola vez
        - un barcode cacheado una vez
        - una regla por nevera+producto 
        - un listId por lista.
        """

        # Solo debe existir un documento agregado por `fridgeId`
        self.inventario.create_index([("fridgeId", ASCENDING)], unique=True)

        self.inventario.create_index([("deviceName", ASCENDING)])

        # Cada `eventId` se registra una sola vez para deduplicar
        self.eventos_procesados.create_index([("eventId", ASCENDING)], unique=True)

        # Un barcode debe resolverse y cachearse una sola vez
        self.productos_cache.create_index([("barcode", ASCENDING)], unique=True)

        # Una nevera solo debe tener una regla activa por producto
        self.reglas_lista_compra.create_index(
            [("fridgeId", ASCENDING), ("barcode", ASCENDING)],
            unique=True,
        )
        self.reglas_lista_compra.create_index([("fridgeId", ASCENDING), ("enabled", ASCENDING)])

        # Cada lista historica tiene id estable propio
        self.lista_compra.create_index([("listId", ASCENDING)], unique=True)
        self.lista_compra.create_index([("fridgeId", ASCENDING), ("status", ASCENDING)])

    def _get_product_name_from_openfoodfacts(self, barcode: str) -> str:
        """
        Consulta OpenFoodFacts y devuelve el nombre del producto.
        """
        url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
        headers = {
            "User-Agent": config.OPENFOODFACTS_USER_AGENT,
        }
        params = {"fields": "product_name"}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=8)
            response.raise_for_status()
            data = response.json()

        except Exception:
            return f"UNKNOWN_{barcode}"

        product = data.get("product")

        if not product:
            return f"UNKNOWN_{barcode}"

        name = product.get("product_name")

        if not name:
            return f"UNKNOWN_{barcode}"

        return str(name).strip()

    def resolve_product_name(self, barcode: str):
        """
        Devuelve un nombre de producto a partir del barcode.

        1. Si empieza por FRESH_, el nombre se deriva del identificador (sin OpenFoodFacts)
        2. revisar cache local en MongoDB
        3. si no existe, consultar Open Food Facts y guardarlo
        4. si todo falla, usar `UNKNOWN_<barcode>`
        """
        if not barcode:
            return "UNKNOWN"

        # Productos frescos detectados por la camara (ej. FRESH_PLATANO)
        if barcode.upper().startswith("FRESH_"):
            nombre = barcode[6:].replace("_", " ").capitalize()
            return f"{nombre} (fresco)"

        cached = self.productos_cache.find_one({"barcode": barcode}, {"_id": 0, "productName": 1})
        cached_name = cached.get("productName") if cached else None
        if cached_name and not self.is_unknown_product_name(cached_name):
            return cached_name

        try:
            product_name = self._get_product_name_from_openfoodfacts(barcode)
        except Exception as exc:
            print(f"No se pudo consultar Open Food Facts para {barcode}: {exc}")
            return f"UNKNOWN_{barcode}"

        if not product_name:
            return f"UNKNOWN_{barcode}"

        if product_name.startswith("UNKNOWN_"):
            return product_name

        # Actualizamos la coleccion
        self.productos_cache.update_one(
            {"barcode": barcode},
            {
                "$set": {
                    "barcode": barcode,
                    "productName": product_name,
                    "updatedAt": datetime.now(timezone.utc),
                },
                "$setOnInsert": {
                    "createdAt": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

        return product_name

    @staticmethod
    def is_unknown_product_name(product_name):
        """
        Indica si un nombre de producto es un placeholder sin resolver
        """
        if not product_name:
            return True

        normalized = str(product_name).strip().upper()
        return normalized == "UNKNOWN" or normalized.startswith("UNKNOWN_")

    def enrich_product_data(self, data: dict | None):
        """
        Enriquece un diccionario con `productName` cuando existe `barcode`.
        """
        enriched_data = dict(data or {})
        barcode = enriched_data.get("barcode")

        product_name = enriched_data.get("productName")

        if barcode and self.is_unknown_product_name(product_name):
            enriched_data["productName"] = self.resolve_product_name(barcode)

        return enriched_data

    @staticmethod
    def build_inventory_document(fridge_id: str, device_name: str, items: list[dict], created_at, updated_at):
        """
        Construye el documento minimo de inventario que queremos persistir.

        Estructura final deseada:
        - fridgeId
        - createdAt
        - deviceName
        - items
        - metrics.inventoryCount
        - metrics.inventoryUniqueItems
        - updatedAt
        """
        return {
            "fridgeId": fridge_id,
            "createdAt": created_at,
            "deviceName": device_name,
            "items": items,
            "metrics": {
                "inventoryCount": sum(int(item.get("qty", 0)) for item in items),
                "inventoryUniqueItems": len(items),
            },
            "updatedAt": updated_at,
        }

    def guardar_inventario_reconstruido(self, fridge_id: str, device_name: str, items: list[dict]):
        """
        Guarda la foto completa reconstruida desde telemetria historica
        """
        now = datetime.now(timezone.utc)
        enriched_items = [self.enrich_product_data(item) for item in items]
        existing = self.get_inventario(fridge_id) or {}
        created_at = existing.get("createdAt", now)

        document = self.build_inventory_document(
            fridge_id=fridge_id,
            device_name=device_name,
            items=enriched_items,
            created_at=created_at,
            updated_at=now,
        )

        # Usamos `replace_one` para que desaparezcan tambien los campos antiguos
        self.inventario.replace_one(
            {"fridgeId": fridge_id},
            document,
            upsert=True,
        )

        return document

    def get_inventario(self, fridge_id: str):
        """
        Devuelve el documento de inventario de una nevera
        """
        return self.inventario.find_one({"fridgeId": fridge_id}, {"_id": 0})

    def list_inventarios(self):
        """
        Devuelve los inventarios de todas las neveras reconstruidas en MongoDB
        """
        return list(self.inventario.find({}, {"_id": 0}).sort("fridgeId", ASCENDING))

    def list_eventos_procesados(self, fridge_id: str, limit: int = 50):
        """
        Devuelve el historial de eventos individuales hasta un limite
        """
        safe_limit = min(max(self.to_positive_int(limit, 50), 1), 200)
        return list(
            self.eventos_procesados.find(
                {"fridgeId": fridge_id},
                {"_id": 0},
            )
            .sort("processedAt", DESCENDING)
            .limit(safe_limit)
        )

    @staticmethod
    def to_positive_int(value, default: int = 0):
        """
        Convierte cualquier valor a entero no negativo de forma segura para
        proteger al backend de payloads malformados
        """
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default

        return parsed if parsed >= 0 else default

    @staticmethod
    def to_bool(value, default: bool = True):
        """
        Convierte valores heterogeneos ("true", "1", "si", "no", 0, bool…)
        a booleano
        """
        if value is None:
            return default
        if isinstance(value, bool):
            return value

        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "si", "sí"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False

        return default

    def ensure_default_shopping_rules(self, fridge_id: str):
        """
        Crea las reglas base de compra para una nevera si aun no existen.
        """
        now = datetime.now(timezone.utc)

        for rule in DEFAULT_SHOPPING_RULES:
            self.reglas_lista_compra.update_one(
                {
                    "fridgeId": fridge_id,
                    "barcode": rule["barcode"],
                },
                {
                    "$setOnInsert": {
                        "fridgeId": fridge_id,
                        "barcode": rule["barcode"],
                        "productName": rule["productName"],
                        "minQty": rule["minQty"],
                        "targetQty": rule["targetQty"],
                        "enabled": rule["enabled"],
                        "source": "DEFAULT_BACKEND_RULE",
                        "createdAt": now,
                        "updatedAt": now,
                    }
                },
                upsert=True,
            )

    def list_reglas_lista_compra(self, fridge_id: str):
        """
        Devuelve todas las reglas de reposicion de una nevera ordenadas por
        barcode, creando las que existen por defecto en el proceso
        """
        self.ensure_default_shopping_rules(fridge_id)
        return list(
            self.reglas_lista_compra.find(
                {"fridgeId": fridge_id},
                {"_id": 0},
            ).sort("barcode", ASCENDING)
        )

    def guardar_regla_lista_compra(self, fridge_id: str, barcode: str, rule_data: dict | None):
        """
        Crea o actualiza una regla de reposicion para un producto
        """
        rule_data = rule_data or {}
        barcode = str(barcode or rule_data.get("barcode") or "").strip()
        if not barcode:
            raise ValueError("La regla de compra necesita un barcode.")

        MAX_QTY = 99
        min_qty = self.to_positive_int(rule_data.get("minQty"), 0)
        target_qty = self.to_positive_int(rule_data.get("targetQty"), min_qty + 1)

        # Comprobamos que la regla tenga sentido y sea correcta
        if target_qty <= min_qty:
            raise ValueError("targetQty debe ser mayor que minQty.")
        if min_qty > MAX_QTY or target_qty > MAX_QTY:
            raise ValueError(f"minQty y targetQty no pueden superar {MAX_QTY}.")

        product_name = self.resolve_product_name(barcode)
        enabled = self.to_bool(rule_data.get("enabled"), True)
        now = datetime.now(timezone.utc)

        # Guardamos la regla
        self.reglas_lista_compra.update_one(
            {
                "fridgeId": fridge_id,
                "barcode": barcode,
            },
            {
                "$set": {
                    "productName": product_name,
                    "minQty": min_qty,
                    "targetQty": target_qty,
                    "enabled": enabled,
                    "source": rule_data.get("source", "API"),
                    "updatedAt": now,
                },
                "$setOnInsert": {
                    "fridgeId": fridge_id,
                    "barcode": barcode,
                    "createdAt": now,
                },
            },
            upsert=True,
        )

        return self.reglas_lista_compra.find_one(
            {
                "fridgeId": fridge_id,
                "barcode": barcode,
            },
            {"_id": 0},
        )

    def eliminar_regla_lista_compra(self, fridge_id: str, barcode: str):
        """
        Borra la regla de reposicion de un producto concreto en una nevera
        """
        result = self.reglas_lista_compra.delete_one(
            {
                "fridgeId": fridge_id,
                "barcode": barcode,
            }
        )
        return {"deleted": result.deleted_count == 1, "fridgeId": fridge_id, "barcode": barcode}

    def get_inventory_qty_by_barcode(self, inventory_doc: dict | None):
        """
        Aplana un documento de inventario a un dict {barcode: cantidad},
        para comparar el stock actual con los umbrales de las reglas
        """
        qty_by_barcode = {}

        for item in (inventory_doc or {}).get("items", []):
            barcode = item.get("barcode")
            if barcode:
                qty_by_barcode[barcode] = self.to_positive_int(item.get("qty"), 0)

        return qty_by_barcode

    def build_lista_compra_items(self, fridge_id: str, inventory_doc: dict | None, affected_barcodes: list[str] | None = None):
        """
        Calcula que productos faltan segun el inventario actual y las reglas.
        """
        self.ensure_default_shopping_rules(fridge_id)
        qty_by_barcode = self.get_inventory_qty_by_barcode(inventory_doc)
        query = {
            "fridgeId": fridge_id,
            "enabled": True,
        }
        if affected_barcodes is not None:
            query["barcode"] = {"$in": affected_barcodes}

        rules = self.reglas_lista_compra.find(query, {"_id": 0}).sort("barcode", ASCENDING)

        shopping_items = []

        for rule in rules:
            barcode = rule.get("barcode")
            current_qty = qty_by_barcode.get(barcode, 0)
            min_qty = self.to_positive_int(rule.get("minQty"), 0)
            target_qty = self.to_positive_int(rule.get("targetQty"), min_qty + 1)

            # Solo se compra si el stock actual está por debajo del objetivo.
            if current_qty > min_qty or current_qty >= target_qty:
                continue

            shopping_items.append(
                {
                    "barcode": barcode,
                    "productName": rule.get("productName") or self.resolve_product_name(barcode),
                    "qtyToBuy": target_qty - current_qty,
                }
            )

        return shopping_items

    @staticmethod
    def merge_lista_compra_items(pending_items: list[dict], recalculated_items: list[dict], affected_barcodes: list[str] | None):
        """
        Combina los items de la lista pendiente con los recien recalculados
        """
        if affected_barcodes is None:
            return recalculated_items

        affected_set = {barcode for barcode in affected_barcodes if barcode}
        merged_items = [
            item
            for item in pending_items
            if item.get("barcode") not in affected_set
        ]
        merged_items.extend(recalculated_items)
        merged_items.sort(key=lambda item: item.get("barcode", ""))
        return merged_items

    def get_pending_lista_compra(self, fridge_id: str):
        """
        Devuelve la lista de compra en estado PENDING de una nevera
        """
        return self.lista_compra.find_one(
            {
                "fridgeId": fridge_id,
                "status": SHOPPING_LIST_STATUS_PENDING,
            },
            {"_id": 0},
            sort=[("_id", DESCENDING)],
        )

    def list_listas_compra(self, fridge_id: str, status: str | None = None):
        """
        Devuelve el historial de listas de compra de una nevera
        
        Opcionalmente podemos filtrar por estado
        PENDING, ORDERED o COMPLETED
        """
        query = {"fridgeId": fridge_id}
        if status:
            query["status"] = status

        return list(
            self.lista_compra.find(
                query,
                {"_id": 0},
            ).sort("_id", DESCENDING)
        )

    def get_lista_compra(self, fridge_id: str, list_id: str):
        """
        Devuelve una lista de compra concreta por su listId
        """
        return self.lista_compra.find_one(
            {
                "fridgeId": fridge_id,
                "listId": list_id,
            },
            {"_id": 0},
        )

    @staticmethod
    def log_productos_anadidos_a_lista_compra(
        fridge_id: str,
        list_id: str,
        items: list[dict],
        source: str,
        trigger_event_id: str | None = None,
    ):
        """
        Deja traza en consola de cada producto añadido a una lista de
        compra, sirve para debuggear
        """
        for item in items:
            print(
                "Producto anadido a lista de compra: "
                f"fridgeId={fridge_id} "
                f"listId={list_id} "
                f"barcode={item.get('barcode')} "
                f"productName={item.get('productName')} "
                f"qtyToBuy={item.get('qtyToBuy')} "
                f"source={source} "
                f"triggerEventId={trigger_event_id}"
            )

    def anadir_item_manual_lista_compra(self, fridge_id: str, barcode: str, qty: int):
        """
        Añade o sobreescribe un item en la lista PENDING de forma manual
        """
        barcode = str(barcode or "").strip()
        if not barcode:
            raise ValueError("El barcode es obligatorio.")

        qty = self.to_positive_int(qty, 0)
        if qty <= 0:
            raise ValueError("La cantidad debe ser mayor que 0.")

        # Resolvemos el nombre del producto antes de añadirlo
        product_name = self.resolve_product_name(barcode)
        new_item = {"barcode": barcode, "productName": product_name, "qtyToBuy": qty}

        pending = self.get_pending_lista_compra(fridge_id)

        if pending:
            items = [i for i in pending.get("items", []) if i.get("barcode") != barcode]
            items.append(new_item)
            items.sort(key=lambda x: x.get("barcode", ""))
            self.lista_compra.replace_one(
                {"listId": pending["listId"]},
                {
                    "listId": pending["listId"],
                    "fridgeId": fridge_id,
                    "status": SHOPPING_LIST_STATUS_PENDING,
                    "items": items,
                },
            )
            return self.get_lista_compra(fridge_id, pending["listId"])

        list_id = uuid.uuid4().hex
        self.lista_compra.insert_one({
            "listId": list_id,
            "fridgeId": fridge_id,
            "status": SHOPPING_LIST_STATUS_PENDING,
            "items": [new_item],
        })
        return self.get_lista_compra(fridge_id, list_id)

    def sincronizar_lista_compra_desde_inventario(self, fridge_id: str, inventory_doc: dict | None, trigger_event_id: str | None = None,
        source: str = "INVENTORY_EVENT", allow_create: bool = True, affected_barcodes: list[str] | None = None):
        """
        Sincroniza la lista de compra pendiente con el inventario actual.

        - si hay productos bajo umbral y no hay lista pendiente, crea una nueva
        - si ya hay lista pendiente, actualiza su contenido
        - si no hay items que comprar, no hace anda
        """
        recalculated_items = self.build_lista_compra_items(
            fridge_id,
            inventory_doc,
            affected_barcodes=affected_barcodes,
        )
        pending = self.get_pending_lista_compra(fridge_id)
        pending_items = (pending or {}).get("items", [])
        items = self.merge_lista_compra_items(
            pending_items=pending_items,
            recalculated_items=recalculated_items,
            affected_barcodes=affected_barcodes,
        )
        pending_barcodes = {
            item.get("barcode")
            for item in pending_items
            if item.get("barcode")
        }

        if not items:
            return {
                "action": "NO_ITEMS",
                "listaCompra": None,
            }

        if pending:
            new_items = [
                item
                for item in recalculated_items
                if item.get("barcode") and item.get("barcode") not in pending_barcodes
            ]
            self.lista_compra.replace_one(
                {"listId": pending["listId"]},
                {
                    "listId": pending["listId"],
                    "fridgeId": fridge_id,
                    "status": SHOPPING_LIST_STATUS_PENDING,
                    "items": items,
                },
            )
            self.log_productos_anadidos_a_lista_compra(
                fridge_id=fridge_id,
                list_id=pending["listId"],
                items=new_items,
                source=source,
                trigger_event_id=trigger_event_id,
            )
            return {
                "action": "UPDATED_PENDING",
                "listaCompra": self.get_lista_compra(fridge_id, pending["listId"]),
            }

        # allow_create siempre sera False cuando el evento es PRODUCT_ADDED
        # Añadir stock nunca debe abrir una lista nueva por sí solo
        if not allow_create:
            return {
                "action": "NEEDS_ITEMS_BUT_CREATE_DISABLED",
                "listaCompra": None,
                "items": items,
            }

        list_id = uuid.uuid4().hex
        document = {
            "listId": list_id,
            "fridgeId": fridge_id,
            "status": SHOPPING_LIST_STATUS_PENDING,
            "items": items,
        }
        self.lista_compra.insert_one(document)
        self.log_productos_anadidos_a_lista_compra(
            fridge_id=fridge_id,
            list_id=list_id,
            items=items,
            source=source,
            trigger_event_id=trigger_event_id,
        )

        return {
            "action": "CREATED_PENDING",
            "listaCompra": self.get_lista_compra(fridge_id, list_id),
        }

    def completar_lista_compra(self, fridge_id: str, list_id: str):
        """
        Marca una lista como COMPLETED

        Solo acepta listas en estado ORDERED (el flujo es PENDING -> ORDERED -> COMPLETED)
        """
        lista = self.lista_compra.find_one(
            {
                "fridgeId": fridge_id,
                "listId": list_id,
                "status": SHOPPING_LIST_STATUS_ORDERED,
            },
            {"_id": 0},
        )

        if not lista:
            return None

        now = datetime.now(timezone.utc)
        self.lista_compra.replace_one(
            {"fridgeId": fridge_id, "listId": list_id},
            {
                "listId": list_id,
                "fridgeId": fridge_id,
                "status": SHOPPING_LIST_STATUS_COMPLETED,
                "items": lista.get("items", []),
                "orderedAt": lista.get("orderedAt"),
                "completedAt": now,
            },
        )

        return self.get_lista_compra(fridge_id, list_id)

    def pedir_online_lista_compra(self, fridge_id: str):
        """
        Marca el documento como ORDERED y registra la fecha del pedido
        """
        now = datetime.now(timezone.utc)
        pending = self.get_pending_lista_compra(fridge_id)
        if not pending:
            return None

        items = pending.get("items", [])
        self.lista_compra.replace_one(
            {"listId": pending["listId"]},
            {
                "listId": pending["listId"],
                "fridgeId": fridge_id,
                "status": SHOPPING_LIST_STATUS_ORDERED,
                "items": items,
                "orderedAt": now,
            },
        )
        lista = self.get_lista_compra(fridge_id, pending["listId"])
        return {
            "message": (
                f"Pedido realizado correctamente. "
                f"{len(items)} producto{'s' if len(items) != 1 else ''} en camino."
            ),
            "listaCompra": lista,
        }

    def registrar_evento_si_no_existe(self, event_id: str, event_doc: dict):
        """
        Registra el evento en la coleccion eventos_procesados

        Devuelve:
        - `True` si el evento puede aplicarse
        - `False` si ese `eventId` ya habia sido procesado antes
        """
        if not event_id:
            return True

        result = self.eventos_procesados.update_one(
            {"eventId": event_id},
            {"$setOnInsert": {"eventId": event_id, **event_doc}},
            upsert=True,
        )
        return result.upserted_id is not None

    def aplicar_evento_individual(self, fridge_id: str, device_name: str, event_id: str | None, event_type: str, payload: dict | None):
        """
        Aplica un evento individual recibido desde la Rule Chain

        Aqui ocurre el camino de tiempo real
        """
        now = datetime.now(timezone.utc)
        payload = self.enrich_product_data(payload)

        # Un evento inválido no debe ocupar su eventId
        if event_type in {"PRODUCT_ADDED", "PRODUCT_REMOVE"}:
            _barcode = payload.get("barcode")
            _qty = self.to_positive_int(payload.get("cantidad"), 0)
            if not _barcode or _qty <= 0:
                return {
                    "status": "INVALID",
                    "fridgeId": fridge_id,
                    "eventId": event_id,
                    "eventType": event_type,
                    "inventario": self.get_inventario(fridge_id),
                    "listaCompra": None,
                }

        event_doc = {
            "fridgeId": fridge_id,
            "processedAt": now,
            "eventType": event_type,
            "payload": payload,
        }

        # Si el eventId ya existe en MongoDB no se aplica dos veces
        inserted = self.registrar_evento_si_no_existe(event_id, event_doc)
        if not inserted:
            current = self.get_inventario(fridge_id)
            return {
                "status": "DUPLICATE",
                "fridgeId": fridge_id,
                "eventId": event_id,
                "inventario": current,
            }

        current = self.get_inventario(fridge_id) or {
            "fridgeId": fridge_id,
            "createdAt": now,
            "deviceName": device_name,
            "items": [],
            "metrics": {
                "inventoryCount": 0,
                "inventoryUniqueItems": 0,
            },
            "updatedAt": now,
        }

        items = current.get("items", [])

        changed = False

        if event_type == "FRIDGE_CREATED":
            # Este evento confirma la existencia de la nevera
            changed = True

        elif event_type in {"PRODUCT_ADDED", "PRODUCT_REMOVE"}:
            barcode = payload.get("barcode")
            qty = self.to_positive_int(payload.get("cantidad"), 0)

            if not barcode or qty <= 0:
                changed = False
            else:
                # Buscar si el producto ya esta en el inventario para sumar o restar sobre el existente.
                existing_item = None
                for item in items:
                    if item.get("barcode") == barcode:
                        existing_item = item
                        break

                if event_type == "PRODUCT_ADDED":
                    if existing_item:
                        existing_item["qty"] = int(existing_item.get("qty", 0)) + qty
                    else:
                        items.append(
                            {
                                "barcode": barcode,
                                "productName": self.resolve_product_name(barcode),
                                "qty": qty,
                            }
                        )
                    changed = True

                elif event_type == "PRODUCT_REMOVE":
                    if not existing_item:
                        changed = False
                    else:
                        # Ai nueva_qty <= 0 el item desaparece del inventario, nunca puede ser negativo
                        nueva_qty = int(existing_item.get("qty", 0)) - qty
                        if nueva_qty > 0:
                            existing_item["qty"] = nueva_qty
                        else:
                            items.remove(existing_item)
                        changed = True

        if not changed:
            return {
                "status": "IGNORED",
                "fridgeId": fridge_id,
                "eventId": event_id,
                "eventType": event_type,
                "inventario": self.get_inventario(fridge_id),
                "listaCompra": None,
            }

        items = [self.enrich_product_data(item) for item in items]
        items.sort(key=lambda item: item.get("barcode", ""))
        document = self.build_inventory_document(
            fridge_id=fridge_id,
            device_name=device_name,
            items=items,
            created_at=current.get("createdAt", now),
            updated_at=now,
        )

        # Persistir la nueva foto del inventario en MongoDB
        self.inventario.replace_one(
            {"fridgeId": fridge_id},
            document,
            upsert=True,
        )

        lista_compra_result = None
        if changed and event_type in {"PRODUCT_ADDED", "PRODUCT_REMOVE"}:

            # Reevaluamos todas las reglas activas
            reglas_activas = self.reglas_lista_compra.find(
                {"fridgeId": fridge_id, "enabled": True},
                {"_id": 0, "barcode": 1},
            )
            affected = {regla["barcode"] for regla in reglas_activas}
            affected.add(payload.get("barcode"))

            # Solo PRODUCT_REMOVE puede abrir una lista nueva
            lista_compra_result = self.sincronizar_lista_compra_desde_inventario(
                fridge_id=fridge_id,
                inventory_doc=document,
                trigger_event_id=event_id,
                source=event_type,
                allow_create=(event_type == "PRODUCT_REMOVE"),
                affected_barcodes=list(affected),
            )

        return {
            "status": "APPLIED" if changed else "IGNORED",
            "fridgeId": fridge_id,
            "eventId": event_id,
            "eventType": event_type,
            "inventario": self.get_inventario(fridge_id),
            "listaCompra": lista_compra_result,
        }
