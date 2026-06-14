"""
Pipeline por frame de inferencia:
  1. Detector de objeto 
  2. Deteccio de codigos de barras
  3. Si no hay barcode, el Ddetector frescos clasifica la ROI.
"""

import os
import time
import logging
from collections import deque

logger = logging.getLogger(__name__)

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

# Si cv2 no estan instalados, el modulo sigue sin deteccion de codigos de barras
_intentar_decodificar = None
_BARCODE_OK = False
try:
    from hardware.camara import intentar_decodificar_avanzado as _intentar_decodificar
    _BARCODE_OK = True
except ImportError:
    logger.warning("hardware.camara no disponible. Deteccion de barcodes desactivada.")

from hardware.detector_frescos import DetectorFrescos
from hardware.detector_objeto   import DetectorObjeto


class CamaraFisica:
    """
    Interfaz unificada de captura y deteccion para la Raspberry Pi
    """

    def __init__(self, camera_index: int = 0, cooldown_seg: float = 4.0, frames_confirmacion: int = 8, mostrar_preview: bool = False,
        usar_frescos: bool = True, usar_yolo: bool = True, frame_skip: int = 2, dir_modelos: "str | None" = None):
        """
        Configura la camara y los detectores sin abrir todavia el dispositivo
        de video

        Permite hacer configuraciones para el control de coste computacional
        """
        self.camera_index = camera_index
        self.cooldown_seg = cooldown_seg
        self.frames_confirmacion = frames_confirmacion
        self.mostrar_preview = mostrar_preview
        self.frame_skip = max(1, int(frame_skip))

        self.usar_barcode = True

        self._cap = None
        self._cooldown: dict = {}
        self._ventana: deque = deque(maxlen=frames_confirmacion)
        self._ultimo_candidato = None
        self._ultimo_estable = False
        self._ultima_bbox = None
        self._contador_frames = 0

        self._detector_frescos = DetectorFrescos(dir_modelos) if usar_frescos else None
        self._detector_objeto  = DetectorObjeto(dir_modelos) if usar_yolo else None


    def iniciar(self):
        """
        Abre el dispositivo de video y lo configura
        """
        if not _CV2_OK:
            raise RuntimeError(
                "OpenCV no esta instalado. Ejecuta: pip install opencv-python"
            )
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"No se pudo abrir la camara {self.camera_index}. "
                "Comprueba que esta conectada y no la usa otro proceso."
            )
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        real_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        real_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("Camara %d iniciada a %dx%d.", self.camera_index, real_w, real_h)

    def detener(self):
        """
        Libera el dispositivo de video y cierra las ventanas de preview
        """
        if self._cap:
            self._cap.release()
            self._cap = None
        if self.mostrar_preview and _CV2_OK:
            cv2.destroyAllWindows()
        logger.info("Camara detenida.")


    def _en_cooldown(self, barcode: str) -> bool:
        """
        Indica si ese barcode se emitio hace menos del cooldown
        """
        ts = self._cooldown.get(barcode)
        return ts is not None and (time.time() - ts) < self.cooldown_seg

    def _registrar_emision(self, barcode: str):
        """
        Anota el instante en que se emitio una deteccion para arrancar el cooldown
        """
        self._cooldown[barcode] = time.time()
        self._ventana.clear()

    def _es_estable(self, barcode: "str | None") -> bool:
        """
        Votacion por ventana deslizante
        
        El producto debe aparecer en >=75% de los ultimos frames para evitar falsos positivos
        """
        self._ventana.append(barcode)
        if barcode is None or len(self._ventana) < self.frames_confirmacion:
            return False
        votos_necesarios = max(1, int(self.frames_confirmacion * 0.75))
        return self._ventana.count(barcode) >= votos_necesarios


    def leer_frame(self) -> "dict | None":
        """
        Captura un frame y ejecuta el pipeline de deteccion
        """
        if self._cap is None:
            raise RuntimeError("Camara no iniciada. Llama a iniciar() primero.")

        ret, frame = self._cap.read()
        if not ret:
            logger.warning("No se pudo leer frame. Comprueba la camara.")
            return None

        self._contador_frames += 1
        procesar = (self._contador_frames % self.frame_skip == 0)

        bbox      = self._ultima_bbox
        candidato = self._ultimo_candidato

        if procesar:
            bbox      = self._localizar_objeto(frame)
            candidato = self._detectar(frame, bbox)
            self._ultima_bbox      = bbox
            self._ultimo_candidato = candidato

        if self.mostrar_preview and _CV2_OK:
            self._dibujar_bbox(frame, bbox, self._ultimo_estable)
            self._dibujar_overlay(frame, candidato, self._ultimo_estable)
            cv2.imshow("Frigorifico | Camara", frame)
            if (
                self._detector_frescos is not None
                and self._detector_frescos.frame_debug is not None
            ):
                cv2.imshow("Frigorifico | Modelo (ROI)", self._detector_frescos.frame_debug)
            cv2.waitKey(1)

        if not procesar:
            return None

        barcode_cand = candidato["barcode"] if candidato else None
        estable      = self._es_estable(barcode_cand)
        self._ultimo_estable = estable

        if not estable or barcode_cand is None:
            return None
        if self._en_cooldown(barcode_cand):
            return None

        self._registrar_emision(barcode_cand)
        logger.info(
            "Deteccion confirmada: %s  [%s]  confianza=%.2f",
            barcode_cand,
            candidato.get("detectionMethod", "?"),
            candidato.get("confidence", 1.0),
        )
        return candidato


    def _localizar_objeto(self, frame) -> "tuple[int, int, int, int] | None":
        """
        Pasa el frame por YOLO y devuelve la bbox del objeto mas confiable
        o None si no hay objeto en escena.
        """
        if self._detector_objeto is None or not self._detector_objeto.disponible:
            h, w = frame.shape[:2]
            return (0, 0, w, h)
        return self._detector_objeto.detectar_bbox(frame)

    def _detectar(self, frame, bbox) -> "dict | None":
        """
        Aplica barcode y si falla, clasificador de frescos la bounding box
        """
        if bbox is None:
            return None

        x1, y1, x2, y2 = bbox
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        resultado_bc = self._detectar_barcode(roi)
        if resultado_bc:
            return resultado_bc
        if self._detector_frescos:
            return self._detector_frescos.detectar(roi)
        return None

    def _detectar_barcode(self, roi) -> "dict | None":
        """
        Intenta leer un codigo de barras
        """
        if not self.usar_barcode or not _BARCODE_OK or _intentar_decodificar is None:
            return None
        codigos, metodo = _intentar_decodificar(roi)
        if codigos:
            barcode_str = codigos[0].data.decode("utf-8")
            print(f"  [BC] {barcode_str}  [{metodo}]")
            return {
                "barcode":         barcode_str,
                "productName":     None,
                "detectionMethod": "BARCODE",
                "confidence":      1.0,
            }
        return None

    # Metodos para facilitar el preview
    @staticmethod
    def _dibujar_bbox(frame, bbox, confirmado: bool):
        """
        Dibuja la bbox detectada por YOLO
        """
        if bbox is None:
            h, w = frame.shape[:2]
            cv2.putText(frame, "Sin objeto a la vista",
                        (w // 2 - 130, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (160, 160, 160), 2)
            return

        x1, y1, x2, y2 = bbox
        color = (0, 255, 0) if confirmado else (0, 180, 255)

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

        largo, grosor = 24, 3
        for (px, sx), (py, sy) in [
            ((x1,  1), (y1,  1)),
            ((x2, -1), (y1,  1)),
            ((x1,  1), (y2, -1)),
            ((x2, -1), (y2, -1)),
        ]:
            cv2.line(frame, (px, py), (px + sx * largo, py), color, grosor)
            cv2.line(frame, (px, py), (px, py + sy * largo), color, grosor)

    @staticmethod
    def _dibujar_overlay(frame, candidato: "dict | None", confirmado: bool):
        """
        Escribe sobre el preview el estado de la deteccion actual
        """
        if candidato is None:
            cv2.putText(frame, "Buscando...", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)
            return

        metodo  = candidato.get("detectionMethod", "?")
        barcode = candidato.get("barcode", "?")
        nombre  = candidato.get("productName") or barcode
        conf    = candidato.get("confidence", 1.0)
        color   = (0, 255, 0) if confirmado else (0, 180, 255)

        cv2.putText(frame, f"{metodo}: {barcode}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        cv2.putText(frame, f"{nombre}  conf={conf:.2f}  {'OK' if confirmado else '...'}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
