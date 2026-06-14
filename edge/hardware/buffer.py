import json
import os
import threading
from pathlib import Path

from hardware.event import Event, EventStatus


class EventBuffer:
    def __init__(self, max_lines=100):
        """
        Inicializa el buffer donde se gaurdaran los eventos antes 
        de eviarse a la plataforma IoT
        """
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self.path = data_dir / "event_buffer.jsonl"

        self.max_lines = max_lines
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _leer_todos(self):
        """
        Lee el JSONL completo y devuelve una lista de objetos Event
        """
        eventos = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        datos = json.loads(line)
                        eventos.append(Event.from_dict(datos))
                    except Exception:
                        continue
        return eventos

    def _escribir_todos(self, eventos):
        """
        Guarda toda la lista de eventos limitando el tamaño máximo del buffer
        """
        pendientes = [ev for ev in eventos if ev.status != EventStatus.COMPLETED]
        completados = [ev for ev in eventos if ev.status == EventStatus.COMPLETED]
        # Conservamos los PENDING enteros y rellenamos con COMPLETED recientes
        # solo si sobra espacio bajo `max_lines`.
        hueco = max(0, self.max_lines - len(pendientes))
        eventos = pendientes + completados[-hueco:] if hueco else pendientes
        eventos = eventos[-self.max_lines:]

        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for ev in eventos:
                f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")

        os.replace(tmp_path, self.path)

    def append_event(self, evento):
        """Añade un nuevo evento al final del buffer"""
        with self._lock:
            eventos = self._leer_todos()
            eventos.append(evento)
            self._escribir_todos(eventos)

    def get_pending_events(self, limit=50):
        """Devuelve solo los eventos con estado PENDING"""
        with self._lock:
            eventos = self._leer_todos()

        pendientes = []
        for ev in eventos:
            if ev.status == EventStatus.PENDING:
                pendientes.append(ev)
                if len(pendientes) >= limit:
                    break

        return pendientes

    def update_event_status(self, event_id, nuevo_estado, add_retry=False):
        """Busca un evento por su ID único y le cambia el estado"""
        with self._lock:
            eventos = self._leer_todos()

            for ev in eventos:
                if ev.event_id == event_id:
                    ev.status = nuevo_estado
                    if add_retry:
                        ev.retry_count += 1
                    break

            self._escribir_todos(eventos)
