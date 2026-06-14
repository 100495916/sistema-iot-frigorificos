import requests

from backend import config

class ThingsBoardApiRestClient:
    """
    Cliente REST simplificado de ThingsBoard

    Responsabilidades:
    - autenticacion
    - listado paginado de dispositivos del tenant
    - lectura de telemetria historica por dispositivo
    """

    def __init__(self) -> None:
        """
        Lee del config la direccion de ThingsBoard y las credenciales
        y construye la URL base de la API REST. No abre ninguna conexion todavia

        Usa los valores de las variables de env a traves de config.py
        """
        self.host = config.THINGSBOARD_HOST
        self.http_port = config.THINGSBOARD_HTTP_PORT
        self.username = config.TB_USERNAME
        self.password = config.TB_PASSWORD
        self.api_key = config.TB_API_KEY
        self.default_limit = config.TB_QUERY_LIMIT
        self.base_url = f"http://{self.host}:{self.http_port}/api"

    def get_auth_headers(self) -> dict:
        """
        Devuelve las cabeceras de autenticacion para la API REST de
        ThingsBoard
        """
        if self.api_key:
            return {"X-Authorization": f"ApiKey {self.api_key}"}

        # Si no tenemos la api_key hacemos un login clasico
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=10,
        )

        # Guardamos las cabeceras
        response.raise_for_status()
        token = response.json()["token"]
        return {"X-Authorization": f"Bearer {token}"}

    def list_devices(self, headers: dict) -> list[dict]:
        """
        Devuelve todos los dispositivos del tenant

        Es la base del sync inicial de todas las neveras
        """
        devices: list[dict] = []
        page = 0

        # ThingsBoard devuelve los dispositivos de 100 en 100
        page_size = 100

        while True:
            response = requests.get(
                f"{self.base_url}/tenant/devices",
                headers=headers,
                params={"pageSize": page_size, "page": page},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            devices.extend(payload.get("data", []))

            if not payload.get("hasNext"):
                break
            page += 1

        # Necesitamos saber cuantos dispositivos reconstruir
        return devices

    def get_device_by_name(self, headers: dict, device_name: str) -> dict:
        """
        Busqueda directa por nombre via GET /api/tenant/devices?deviceName=X
        """
        response = requests.get(
            f"{self.base_url}/tenant/devices",
            headers=headers,
            params={"deviceName": device_name},
            timeout=10,
        )
        if response.status_code == 404:
            raise ValueError(f"No se encontro el dispositivo '{device_name}' en ThingsBoard.")
        
        response.raise_for_status()
        return response.json()

    @staticmethod
    def get_device_id(device: dict, device_name: str) -> str:
        """
        Extrae el UUID interno de ThingsBoard de un dict de dispositivo
        """
        tb_device_id = device.get("id", {}).get("id")
        if not tb_device_id:
            raise ValueError(f"No se pudo obtener el id interno del dispositivo '{device_name}'.")
        
        return tb_device_id

    @staticmethod
    def get_device_name(device: dict) -> str:
        """
        Extrae el nombre de un dict de dispositivo de ThingsBoard
        """
        return device.get("name") or "unknown_device"

    def get_historical_telemetry(self, headers: dict, device_id: str, start_ts: int, end_ts: int, limit: int | None = None) -> dict:
        """
        Descarga la telemetria historica de un dispositivo en el rango
        [start_ts, end_ts]

        Es lo que usa el backend para la reconstrucción
        """

        # Pedimos solo los 5 campos que le interesa al backend
        params = {
            "keys": ",".join(["eventId", "eventType", "eventPayload", "eventTs", "fridgeId"]),
            "startTs": start_ts,
            "endTs": end_ts,
            "limit": limit or self.default_limit,
            "agg": "NONE",
        }

        response = requests.get(
            f"{self.base_url}/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            headers=headers,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
