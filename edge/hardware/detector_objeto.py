import logging
import os

logger = logging.getLogger(__name__)

try:
    import numpy as np
    import cv2
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

try:
    import onnxruntime as _ort
    _ORT_OK = True
except ImportError:
    _ort = None
    _ORT_OK = False


DIR_AQUI = os.path.dirname(os.path.abspath(__file__))
DIR_MODELOS_DEFAULT = os.path.join(DIR_AQUI, "modelos")
NOMBRE_MODELO = "yolov8n.onnx"


class DetectorObjeto:
    """
    Localiza la bounding box del objeto mas confiable en el frame
    usando YOLOv8n preentrenado
    """

    INPUT_SIZE = 320
    CONF_THRES = 0.25
    IOU_THRES = 0.45
    PADDING_PCT = 0.10

    def __init__(self, dir_modelos: "str | None" = None, input_size: int = INPUT_SIZE):
        """
        Localiza el modelo yolov8n.onnx en dir_modelos 
        (o lo descarga y exporta la primera vez si ultralytics esta instalado)
        """
        self._dir          = dir_modelos or DIR_MODELOS_DEFAULT
        self._input_size   = input_size
        self._session      = None
        self._input_name   = None
        self.disponible    = False

        if not _DEPS_OK:
            logger.warning("numpy/opencv no disponibles. DetectorObjeto desactivado.")
            return
        if not _ORT_OK:
            logger.warning("onnxruntime no instalado. DetectorObjeto desactivado.")
            return

        ruta = os.path.join(self._dir, NOMBRE_MODELO)
        if not os.path.exists(ruta):
            ruta = self._descargar_y_exportar(ruta)
            if ruta is None:
                return

        self._cargar_sesion(ruta)

    def _descargar_y_exportar(self, ruta_destino: str) -> "str | None":
        """
        Descarga yolov8n.pt y lo exporta a ONNX usando ultralytics
        """
        os.makedirs(self._dir, exist_ok=True)
        try:
            from ultralytics import YOLO   # type: ignore
        except ImportError:
            logger.warning("ultralytics no instalado")
            return None

        print(f"[DetectorObjeto] yolov8n.onnx no encontrado. Descargando y exportando")
        try:
            modelo = YOLO("yolov8n.pt")
            ruta_exportada = modelo.export(format="onnx", imgsz=self._input_size,
                                           opset=12, simplify=True)
            
            if os.path.abspath(ruta_exportada) != os.path.abspath(ruta_destino):
                os.replace(ruta_exportada, ruta_destino)

            for candidato in ("yolov8n.pt", os.path.join(os.getcwd(), "yolov8n.pt")):
                if os.path.exists(candidato):
                    try:
                        os.remove(candidato)
                    except OSError:
                        pass

            logger.info("yolov8n.onnx exportado en %s", ruta_destino)
            return ruta_destino
        except Exception as exc:
            logger.error("Fallo al exportar yolov8n.onnx: %s", exc)
            return None

    def _cargar_sesion(self, ruta_onnx: str):
        """
        Crea la sesion de ONNX Runtime con todas las optimizaciones de
        grafo activadas
        """
        try:
            opts = _ort.SessionOptions()
            opts.graph_optimization_level = _ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session    = _ort.InferenceSession(ruta_onnx, opts)
            self._input_name = self._session.get_inputs()[0].name
            self.disponible  = True
            logger.info("DetectorObjeto [YOLOv8n %dx%d] listo.",
                        self._input_size, self._input_size)
        except Exception as exc:
            logger.error("No fue posible cargar yolov8n.onnx: %s", exc)
            self.disponible = False

    def detectar_bbox(self, frame) -> "tuple[int, int, int, int] | None":
        """
        Devuelve (x1, y1, x2, y2) del objeto con mayor confianza en
        coordenadas del frame original
        """
        if not self.disponible:
            return None

        h0, w0 = frame.shape[:2]
        tensor, escala, dx, dy = self._letterbox(frame)

        try:
            salida = self._session.run(None, {self._input_name: tensor})[0]
        except Exception as exc:
            logger.error("Inferencia YOLO fallida: %s", exc)
            return None

        pred = salida[0].T
        cajas_xywh = pred[:, :4]
        scores_cls = pred[:, 4:]
        scores     = scores_cls.max(axis=1)

        mascara = scores > self.CONF_THRES
        if not mascara.any():
            return None

        cajas_xywh = cajas_xywh[mascara]
        scores     = scores[mascara]

        cajas_xywh[:, 0] -= cajas_xywh[:, 2] / 2.0
        cajas_xywh[:, 1] -= cajas_xywh[:, 3] / 2.0

        indices = cv2.dnn.NMSBoxes(
            cajas_xywh.tolist(), scores.tolist(),
            self.CONF_THRES, self.IOU_THRES,
        )
        if len(indices) == 0:
            return None
        indices = np.array(indices).flatten()

        # Coger la caja con mayor confianza
        mejor = indices[int(np.argmax(scores[indices]))]
        x, y, w, h = cajas_xywh[mejor]


        x1 = (x - dx) / escala
        y1 = (y - dy) / escala
        x2 = (x + w - dx) / escala
        y2 = (y + h - dy) / escala

        # Aplicar padding y clamp al frame
        pw = (x2 - x1) * self.PADDING_PCT
        ph = (y2 - y1) * self.PADDING_PCT
        x1 = max(0,  int(round(x1 - pw)))
        y1 = max(0,  int(round(y1 - ph)))
        x2 = min(w0, int(round(x2 + pw)))
        y2 = min(h0, int(round(y2 + ph)))

        if x2 - x1 < 10 or y2 - y1 < 10:
            return None
        return x1, y1, x2, y2


    def _letterbox(self, frame):
        """
        Redimensiona el frame al tamano de entrada preservando aspect
        ratio y rellenando con gris
        """
        h, w = frame.shape[:2]
        size = self._input_size
        escala = min(size / h, size / w)
        nh, nw = int(round(h * escala)), int(round(w * escala))
        dx = (size - nw) // 2
        dy = (size - nh) // 2

        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        canvas[dy:dy + nh, dx:dx + nw] = cv2.resize(
            frame, (nw, nh), interpolation=cv2.INTER_LINEAR,
        )

        img = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.expand_dims(img.transpose(2, 0, 1), axis=0)  # NCHW
        return tensor, escala, dx, dy
