import json
import os
import random
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv

from hardware.buffer import EventBuffer
from hardware.event import Event, EventStatus, EventType


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

# Cargamos las variables de entorno con valores default
THINGSBOARD_HOST = os.getenv("THINGSBOARD_HOST", "127.0.0.1")
THINGSBOARD_HTTP_PORT = os.getenv("THINGSBOARD_HTTP_PORT", "8080")
THINGSBOARD_MQTT_PORT = int(os.getenv("THINGSBOARD_MQTT_PORT", 1883))

FRIDGE_ID = os.getenv("FRIDGE_ID", "fridge_defecto")
PROVISION_KEY = os.getenv("PROVISION_KEY", "")
PROVISION_SECRET = os.getenv("PROVISION_SECRET", "")

DATA_DIR = os.getenv("DATA_DIR", "./data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
PROVISION_TIMEOUT_SECONDS = 10
MQTT_PUBLISH_TIMEOUT_SECONDS = 5.0

# Catálogo para simulacion
CATALOGO_ENVASADOS = [
    {"nombre": "Leche entera Pascual",  "barcode": "8410128010096"},
    {"nombre": "Cocacola",              "barcode": "5449000000996"},
    {"nombre": "Cocacola Zero",         "barcode": "5449000133328"},
    {"nombre": "Huevos camperos",       "barcode": "8437015354019"},
    {"nombre": "Nutella",               "barcode": "3017620422003"},
    {"nombre": "Philadelphia Original", "barcode": "7622210103314"},
    {"nombre": "Oreo",                  "barcode": "7622300336738"},
    {"nombre": "Spaghetti Barilla",     "barcode": "8076800195057"},
    {"nombre": "Ketchup",               "barcode": "8480000235794"},
    {"nombre": "Mars",                  "barcode": "5000159407236"},
    {"nombre": "Bimbo",                 "barcode": "3228857000852"},
    {"nombre": "Cookies chocolate",     "barcode": "3560070048786"},
    {"nombre": "Pechuga de Pavo",       "barcode": "8480000057105"},
    {"nombre": "Jamon Serrano",         "barcode": "8421395357500"},
    {"nombre": "Salmorejo",             "barcode": "5410188032161"},

    # Barcode inexistente a proposito para comprobar el camino UNKNOWN_<barcode>
    {"nombre": "Producto desconocido",  "barcode": "0000000000001"},
]

# Catalogo de productos frescos para simulacion
CATALOGO_FRESCOS = [
    {"nombre": "Manzana",    "barcode": "FRESH_MANZANA"},
    {"nombre": "Platano",    "barcode": "FRESH_PLATANO"},
    {"nombre": "Fresa",      "barcode": "FRESH_FRESA"},
    {"nombre": "Naranja",    "barcode": "FRESH_NARANJA"},
    {"nombre": "Pera",       "barcode": "FRESH_PERA"},
    {"nombre": "Tomate",     "barcode": "FRESH_TOMATE"},
    {"nombre": "Aguacate",   "barcode": "FRESH_AGUACATE"},
]


buffer = EventBuffer(max_lines=100)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_connected_event = threading.Event()
device_created_at = None


def utc_now_iso():
    """
    Devuelve la fecha y hora actual
    """
    return datetime.now(timezone.utc).isoformat()


def cargar_configuracion_local():
    """
    Lee config.json del directorio de datos y devuelve su contenido como dict
    
    Este fichero guarda la identidad persistente del dispositivo (token de
    acceso y fecha de creacion)
    """
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        print(f"[{FRIDGE_ID}] No se pudo leer {CONFIG_FILE}: {exc}")

    return {}


def guardar_configuracion_local(access_token, created_at):
    """
    Persiste el token de acceso MQTT y la fecha de creacion en config.json
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "access_token": access_token,
                "created_at": created_at,
            },
            f,
        )

def validar_configuracion():
    """
    Comprueba que las variables de entorno necesarias estan configuradas antes de arrancar
    """
    errores = []

    if not THINGSBOARD_HOST:
        errores.append("THINGSBOARD_HOST esta vacio.")

    if not PROVISION_KEY or PROVISION_KEY == "TU_CLAVE_DE_THINGSBOARD":
        errores.append("PROVISION_KEY no esta configurada.")

    if not PROVISION_SECRET or PROVISION_SECRET == "TU_SECRETO_DE_THINGSBOARD":
        errores.append("PROVISION_SECRET no esta configurado.")

    if THINGSBOARD_MQTT_PORT <= 0:
        errores.append("THINGSBOARD_MQTT_PORT no es valido.")

    if errores:
        print(f"[{FRIDGE_ID}] Configuracion invalida:")
        for error in errores:
            print(f" - {error}")
        return False

    return True


def obtener_token():
    """
    Obtiene las credenciales MQTT de la nevera 
    
    Si existe un token guardado en config.json lo reutiliza  

    Si no, solicita el auto-provisioning a ThingsBoard via HTTP
    """
    config = cargar_configuracion_local()
    access_token = config.get("access_token")
    created_at = config.get("created_at")

    if access_token:
        # Si recuperamos el token local, evitamos reprovisionar la nevera
        if not created_at:
            created_at = utc_now_iso()
            guardar_configuracion_local(access_token, created_at)
            print(f"[{FRIDGE_ID}] Configuracion local completada con created_at.")
        else:
            print(f"[{FRIDGE_ID}] Token cargado desde almacenamiento local.")
        return access_token, created_at, False

    print(f"[{FRIDGE_ID}] Dispositivo no registrado. Solicitando auto-provisioning...")
    url = f"http://{THINGSBOARD_HOST}:{THINGSBOARD_HTTP_PORT}/api/v1/provision"

    payload = {
        "provisionDeviceKey": PROVISION_KEY,
        "provisionDeviceSecret": PROVISION_SECRET,
        "deviceName": FRIDGE_ID,
    }

    try:
        response = requests.post(url, json=payload, timeout=PROVISION_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "SUCCESS":
            print(f"[{FRIDGE_ID}] Error en provisioning: {data.get('errorMsg')}")
            return None, None, False

        nuevo_token = data.get("credentialsValue")
        created_at = utc_now_iso()
        guardar_configuracion_local(nuevo_token, created_at)
        print(f"[{FRIDGE_ID}] Registro exitoso. Token guardado en {CONFIG_FILE}.")
        return nuevo_token, created_at, True
    
    except Exception as exc:
        print(f"[{FRIDGE_ID}] Fallo de red al contactar con ThingsBoard: {exc}")
        return None, None, False


def _wait_for_publish_safe(result):
    """
    Espera la confirmacion del broker MQTT con timeout
    """
    try:
        result.wait_for_publish(timeout=MQTT_PUBLISH_TIMEOUT_SECONDS)
    except Exception as exc:
        print(f"[{FRIDGE_ID}] wait_for_publish fallo: {exc}")
        return False
    return result.is_published()


def publicar_atributos_iniciales(created_at):
    """
    Publica los atributos de identidad de la nevera (fridgeId y createdAt)
    en ThingsBoard via MQTT
    """
    payload = {
        "fridgeId": FRIDGE_ID,
        "createdAt": created_at,
    }

    result = client.publish("v1/devices/me/attributes", json.dumps(payload), qos=1)
    if _wait_for_publish_safe(result):
        print(f"[{FRIDGE_ID}] Atributos iniciales publicados en ThingsBoard.")
        return True

    print(f"[{FRIDGE_ID}] No se pudieron publicar los atributos iniciales.")
    return False

def publicar_evento_en_thingsboard(evento):
    """
    Envia un evento como telemetria MQTT a ThingsBoard
    """
    payload = {
        "eventId": evento.event_id,
        "fridgeId": evento.fridge_id,
        "eventType": evento.type,
        "eventTs": evento.ts,
        "eventStatus": EventStatus.COMPLETED,
        "eventPayload": evento.payload,
        "retryCount": evento.retry_count,
    }

    # doorStatus es un key independiente de eventType para que eventos como PRODUCT_ADDED no rompan 
    # la condicion de duracion de la alarma de puerta.
    if evento.type == EventType.DOOR_OPEN:
        payload["doorStatus"] = "OPEN"
    elif evento.type == EventType.DOOR_CLOSE:
        payload["doorStatus"] = "CLOSED"

    # Publicamos hacia ThingsBoard
    result = client.publish("v1/devices/me/telemetry", json.dumps(payload), qos=1)
    return _wait_for_publish_safe(result)


def sincronizar_estado_inicial(is_new_device: bool):
    """
    Publica los atributos iniciales solo cuando la nevera es nueva.
    Si el dispositivo ya existia en ThingsBoard no se repite esa
    informacion, evitando sobrescribir datos del primer arranque.
    """
    if is_new_device and device_created_at:
        publicar_atributos_iniciales(device_created_at)


def on_connect(client, userdata, flags, reason_code, properties):
    """
    Callback de paho-mqtt al establecerse la conexion con ThingsBoard
    """
    if reason_code == 0:
        print(f"[{FRIDGE_ID}] Conectado a ThingsBoard por MQTT.")
        mqtt_connected_event.set()
    else:
        print(f"[{FRIDGE_ID}] Error de conexion MQTT. Codigo: {reason_code}")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    """
    Callback de paho-mqtt cuando se pierde la conexion con ThingsBoard
    """
    print(f"[{FRIDGE_ID}] Desconectado de ThingsBoard.")
    mqtt_connected_event.clear()


def crear_evento_producto(event_type, producto, cantidad):
    """
    Construye un evento de producto (PRODUCT_ADDED o PRODUCT_REMOVE) con el
    payload minimo que espera el backend
    """
    payload = {
        "barcode": producto["barcode"],
        "cantidad": cantidad,
    }
    return Event(fridge_id=FRIDGE_ID, event_type=event_type, payload=payload)


def guardar_evento_producto(event_type, producto, cantidad):
    """
    Crea un evento de producto y lo deja en el buffer local de envio
    """
    evento = crear_evento_producto(event_type, producto, cantidad)
    buffer.append_event(evento)
    return evento


def productos_con_stock(productos, inventario_simulado):
    """
    Filtra una lista de productos del catalogo y devuelve solo los que
    tienen stock disponible
    """
    return [
        producto
        for producto in productos
        if inventario_simulado.get(producto["barcode"], 0) > 0
    ]


def _perfil_nevera(fridge_id: str) -> dict:
    """
    Genera un perfil de comportamiento estable y determinista a partir del
    FRIDGE_ID
    """
    rng = random.Random(fridge_id)

    n_env = rng.randint(4, 7)
    envasados = rng.sample(CATALOGO_ENVASADOS, n_env)

    n_fresh = rng.randint(1, 3)
    frescos = rng.sample(CATALOGO_FRESCOS, n_fresh)

    productos = envasados + frescos

    return {
        "rng": rng,
        "productos": productos,
        "stock_repo": {p["barcode"]: rng.randint(3, 8) for p in productos},
        "intervalo_ciclo_seg": rng.uniform(20, 60),
        "espera_puerta_normal_seg": rng.uniform(2, 6),
        "prob_alarma": rng.uniform(0.10, 0.30),
        "espera_alarma_seg": rng.uniform(35, 90),

        # Con esta probabilidad se consumen 2 productos en la misma apertura
        "prob_consumo_multiple": rng.uniform(0.20, 0.40),

        # Con esta probabilidad se repone algún producto agotado sin que la nevera esté completamente vacía
        "prob_reposicion_parcial": rng.uniform(0.15, 0.35),
    }


def simulacion():
    """
    Simulacion de la nevera 
    - ciclos de consumo/reposicion
    - eventos de puerta y alarmas ocasionales

    Comportamiento por ciclo (cada apertura de puerta):
    - Si la nevera está completamente vacía → reposicion total
    - Si hay productos agotados → toca reposicion parcial
    - A veces se consumen 2 productos en la misma apertura en lugar de 1
    """
    perfil = _perfil_nevera(FRIDGE_ID)
    rng = perfil["rng"]
    inventario_simulado = {p["barcode"]: 0 for p in perfil["productos"]}
    turno = 0

    nombres = [p["nombre"] for p in perfil["productos"]]
    print(
        f"[{FRIDGE_ID}] Perfil nevera — productos: {nombres}, "
        f"ciclo: {perfil['intervalo_ciclo_seg']:.0f}s, "
        f"prob_alarma: {perfil['prob_alarma']:.0%}"
    )

    while True:
        # Esperar antes del siguiente ciclo
        espera = perfil["intervalo_ciclo_seg"] + rng.uniform(-5, 10)
        time.sleep(max(5.0, espera))

        # Abrir puerta
        buffer.append_event(Event(fridge_id=FRIDGE_ID, event_type=EventType.DOOR_OPEN))
        print(f"[{FRIDGE_ID}] Puerta: ABIERTA")
        procesar_buffer()

        # Decidir si la puerta se queda olvidada abierta
        if rng.random() < perfil["prob_alarma"]:
            espera_open = perfil["espera_alarma_seg"] + rng.uniform(0, 20)
            print(f"[{FRIDGE_ID}] Puerta olvidada abierta ({espera_open:.0f}s)...")
            time.sleep(espera_open)
        else:
            time.sleep(perfil["espera_puerta_normal_seg"] + rng.uniform(0, 3))

        # Reposicion: total si vacia o parcial espontanea
        vacia = not any(v > 0 for v in inventario_simulado.values())
        agotados = [
            p for p in perfil["productos"]
            if inventario_simulado.get(p["barcode"], 0) == 0
        ]

        if vacia:
            turno = 0
            print(f"[{FRIDGE_ID}] Nevera vacia. Reponiendo todos los productos...")
            for producto in perfil["productos"]:
                cantidad = perfil["stock_repo"][producto["barcode"]]
                inventario_simulado[producto["barcode"]] = cantidad
                guardar_evento_producto(EventType.PRODUCT_ADDED, producto, cantidad)

                print(f"[{FRIDGE_ID}] + Reposicion total: {producto['nombre']} x{cantidad}")
                procesar_buffer()
                time.sleep(1)

        elif agotados and rng.random() < perfil["prob_reposicion_parcial"]:
            n_repo = rng.randint(1, len(agotados))
            a_reponer = rng.sample(agotados, n_repo)

            print(f"[{FRIDGE_ID}] Reposicion parcial ({len(a_reponer)} producto/s)...")
            for producto in a_reponer:
                cantidad = rng.randint(2, perfil["stock_repo"][producto["barcode"]])
                inventario_simulado[producto["barcode"]] = cantidad
                guardar_evento_producto(EventType.PRODUCT_ADDED, producto, cantidad)
                print(f"[{FRIDGE_ID}] + Reposicion parcial: {producto['nombre']} x{cantidad}")
                procesar_buffer()
                time.sleep(1)

        # Consumir productos
        n_consume = 2 if rng.random() < perfil["prob_consumo_multiple"] else 1
        for _ in range(n_consume):
            disponibles = productos_con_stock(perfil["productos"], inventario_simulado)
            if not disponibles:
                break
            producto = disponibles[turno % len(disponibles)]

            qty_actual = inventario_simulado[producto["barcode"]]
            inventario_simulado[producto["barcode"]] = max(0, qty_actual - 1)
            guardar_evento_producto(EventType.PRODUCT_REMOVE, producto, 1)

            print(
                f"[{FRIDGE_ID}] - Consumo: {producto['nombre']}. "
                f"Quedan {inventario_simulado[producto['barcode']]}."
            )
            turno += 1
            time.sleep(1)
            procesar_buffer()

        # Cerrar puerta
        buffer.append_event(Event(fridge_id=FRIDGE_ID, event_type=EventType.DOOR_CLOSE))
        print(f"[{FRIDGE_ID}] Puerta: CERRADA")
        procesar_buffer()


def procesar_buffer():
    """
    Intenta publicar en ThingsBoard todos los eventos pendientes del buffer
    local
    """
    pendientes = buffer.get_pending_events(limit=10)

    for evento in pendientes:
        try:
            if publicar_evento_en_thingsboard(evento):
                print(f"[{FRIDGE_ID}] -> Enviado a TB: {evento.type}")
                buffer.update_event_status(evento.event_id, EventStatus.COMPLETED)
            else:
                raise Exception("El servidor MQTT no confirmo la recepcion.")

        except Exception as exc:
            print(f"[{FRIDGE_ID}] Error al enviar a TB: {exc}")
            buffer.update_event_status(
                evento.event_id,
                EventStatus.PENDING,
                add_retry=True,
            )


def main():
    """
    Punto de entrada del gemelo digital
     
    Orquesta el arranque completo
    """
    global device_created_at

    print(f"[{FRIDGE_ID}] Iniciando Gemelo Digital...")

    if not validar_configuracion():
        print(f"[{FRIDGE_ID}] Corrige la configuracion antes de volver a arrancar.")
        return

    access_token, created_at, is_new_device = obtener_token()
    if not access_token:
        print("No se pudo obtener el token. Saliendo...")
        return

    device_created_at = created_at

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.username_pw_set(access_token)

    # La nevera operativa habla con ThingsBoard por MQTT
    client.connect(THINGSBOARD_HOST, THINGSBOARD_MQTT_PORT, 60)
    client.loop_start()

    if not mqtt_connected_event.wait(timeout=10):
        print(f"[{FRIDGE_ID}] Timeout esperando la conexion MQTT con ThingsBoard.")
        client.loop_stop()
        client.disconnect()
        return

    if is_new_device:
        print(f"[{FRIDGE_ID}] Conexion MQTT confirmada. Publicando atributos iniciales...")
    else:
        print(f"[{FRIDGE_ID}] Conexion MQTT confirmada. Nevera conocida, no se publican atributos iniciales.")
    sincronizar_estado_inicial(is_new_device)

    try:
        if is_new_device:
            evento_inicio = Event(fridge_id=FRIDGE_ID, event_type=EventType.FRIDGE_CREATED)
            buffer.append_event(evento_inicio)
            print(f"[{FRIDGE_ID}] Evento inicial guardado en buffer: {evento_inicio.type}")

            # Lo enviarmos directamente, sin esperar al primer ciclo de simulacion
            procesar_buffer()
            time.sleep(1)
        else:
            print(f"[{FRIDGE_ID}] Nevera ya conocida. No se genera FRIDGE_CREATED.")
            time.sleep(1)

        simulacion()

    except KeyboardInterrupt:
        print(f"[{FRIDGE_ID}] Apagando simulador...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()