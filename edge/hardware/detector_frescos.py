import json
import logging
import os

logger = logging.getLogger(__name__)

_ort      = None
_ORT_OK   = False

try:
    import onnxruntime as _ort
    _ORT_OK = True
except ImportError:
    pass

try:
    import numpy as np
    import cv2
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False


DIR_AQUI = os.path.dirname(os.path.abspath(__file__))
DIR_MODELOS_DEFAULT = os.path.join(DIR_AQUI, "modelos")

# Diccionario de clases
CLASES_FRUITS360: dict = {
    # ---- Frutas ----
    "apple":        ("FRESH_MANZANA",     "Manzana"),
    "banana":       ("FRESH_PLATANO",     "Platano"),
    "cherry":       ("FRESH_CEREZA",      "Cereza"),
    "clementine":   ("FRESH_CLEMENTINA",  "Clementina"),
    "coconut":      ("FRESH_COCO",        "Coco"),
    "fig":          ("FRESH_HIGO",        "Higo"),
    "grape":        ("FRESH_UVA",         "Uva"),
    "grapefruit":   ("FRESH_POMELO",      "Pomelo"),
    "guava":        ("FRESH_GUAYABA",     "Guayaba"),
    "kiwi":         ("FRESH_KIWI",        "Kiwi"),
    "lemon":        ("FRESH_LIMON",       "Limon"),
    "lime":         ("FRESH_LIMA",        "Lima"),
    "lychee":       ("FRESH_LICHI",       "Lichi"),
    "mandarine":    ("FRESH_MANDARINA",   "Mandarina"),
    "mango":        ("FRESH_MANGO",       "Mango"),
    "melon":        ("FRESH_MELON",       "Melon"),
    "nectarine":    ("FRESH_NECTARINA",   "Nectarina"),
    "orange":       ("FRESH_NARANJA",     "Naranja"),
    "papaya":       ("FRESH_PAPAYA",      "Papaya"),
    "passion":      ("FRESH_MARACUYA",    "Maracuya"),
    "peach":        ("FRESH_MELOCOTON",   "Melocoton"),
    "pear":         ("FRESH_PERA",        "Pera"),
    "pineapple":    ("FRESH_PINA",        "Pina"),
    "pitahaya":     ("FRESH_PITAYA",      "Pitaya"),
    "plum":         ("FRESH_CIRUELA",     "Ciruela"),
    "pomegranate":  ("FRESH_GRANADA",     "Granada"),
    "blackberry":   ("FRESH_MORA",        "Mora"),
    "raspberry":    ("FRESH_FRAMBUESA",   "Frambuesa"),
    "redcurrant":   ("FRESH_GROSELLA",    "Grosella"),
    "gooseberry":   ("FRESH_GROSELLA",    "Grosella"),
    "salak":        ("FRESH_SALAK",       "Salak"),
    "strawberry":   ("FRESH_FRESA",       "Fresa"),
    "tamarillo":    ("FRESH_TAMARILLO",   "Tamarillo"),
    "tangelo":      ("FRESH_TANGELO",     "Tangelo"),
    "watermelon":   ("FRESH_SANDIA",      "Sandia"),
    "cantaloupe":   ("FRESH_MELON",       "Melon"),
    "cherimoya":    ("FRESH_CHIRIMOYA",   "Chirimoya"),
    "quince":       ("FRESH_MEMBRILLO",   "Membrillo"),
    "dates":        ("FRESH_DATIL",       "Datil"),
    "carambola":    ("FRESH_CARAMBOLA",   "Carambola"),
    "caju":         ("FRESH_ANACARDO",    "Anacardo"),
    "almond":       ("FRESH_ALMENDRA",    "Almendra"),
    "pistachio":    ("FRESH_PISTACHO",    "Pistacho"),
    "peanut":       ("FRESH_CACAHUETE",   "Cacahuete"),

    # ---- Verduras ----
    "artichoke":    ("FRESH_ALCACHOFA",   "Alcachofa"),
    "avocado":      ("FRESH_AGUACATE",    "Aguacate"),
    "beetroot":     ("FRESH_REMOLACHA",   "Remolacha"),
    "broccoli":     ("FRESH_BROCOLI",     "Brocoli"),
    "cabbage":      ("FRESH_REPOLLO",     "Repollo"),
    "carrot":       ("FRESH_ZANAHORIA",   "Zanahoria"),
    "cauliflower":  ("FRESH_COLIFLOR",    "Coliflor"),
    "chestnut":     ("FRESH_CASTANA",     "Castana"),
    "corn":         ("FRESH_MAIZ",        "Maiz"),
    "cucumber":     ("FRESH_PEPINO",      "Pepino"),
    "eggplant":     ("FRESH_BERENJENA",   "Berenjena"),
    "garlic":       ("FRESH_AJO",         "Ajo"),
    "ginger":       ("FRESH_JENGIBRE",    "Jengibre"),
    "mushroom":     ("FRESH_CHAMPINON",   "Champinon"),
    "onion":        ("FRESH_CEBOLLA",     "Cebolla"),
    "pepper":       ("FRESH_PIMIENTO",    "Pimiento"),
    "potato":       ("FRESH_PATATA",      "Patata"),
    "pumpkin":      ("FRESH_CALABAZA",    "Calabaza"),
    "squash":       ("FRESH_CALABAZA",    "Calabaza"),
    "tomato":       ("FRESH_TOMATE",      "Tomate"),
    "zucchini":     ("FRESH_CALABACIN",   "Calabacin"),
    "beans":        ("FRESH_JUDIAS",      "Judias"),
}

# Normalizacion ImageNet usada por EfficientNet B0
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32) if _DEPS_OK else None
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32) if _DEPS_OK else None


class DetectorFrescos:
    """
    Identifica productos frescos con un modelo ONNX propio (Fruits-360)

    Espera recibir un frame ya recortado al objeto

    Flujo de deteccion:
      1. Redimensionar el ROI a 224x224
      2. Ejecutar inferencia ONNX
      3. Clase con mayor probabilidad (top-1)
      4. Si supera CONFIANZA_MINIMA y es un alimento conocido, devolver resultado
    """

    CONFIANZA_MINIMA = 0.85
    INPUT_SIZE       = (224, 224)

    def __init__(self, dir_modelos: "str | None" = None):
        """
        Prepara el clasificador y carga el modelo ONNX desde dir_modelos
        """
        self._dir = dir_modelos or DIR_MODELOS_DEFAULT
        self._motor = None
        self._session = None
        self._etiquetas: list = []
        self._clases_dict: dict = {}
        self._input_name   = None
        self._preprocessing = 'imagenet'
        self.frame_debug = None

        if not _DEPS_OK:
            logger.warning("numpy/opencv no disponibles. DetectorFrescos desactivado.")
            return

        self._inicializar()

    def _inicializar(self):
        """
        Comprueba que onnxruntime esta instalado y que existen el fichero
        .onnx y su JSON de etiquetas
        """
        ruta_onnx   = os.path.join(self._dir, "modelo_frutas.onnx")
        ruta_labels = os.path.join(self._dir, "modelo_frutas_labels.json")

        if not _ORT_OK:
            print("[DetectorFrescos] ERROR: onnxruntime no instalado. Ejecuta: pip install onnxruntime")
            return

        if not os.path.exists(ruta_onnx) or not os.path.exists(ruta_labels):
            print(f"[DetectorFrescos] ERROR: modelo ONNX no encontrado en {self._dir}")
            print(" Genera el modelo ejecutando el notebook tfg_entrenamiento_modelo.ipynb")
            return

        self._inicializar_onnx(ruta_onnx, ruta_labels)

    def _inicializar_onnx(self, ruta_onnx: str, ruta_labels: str):
        """
        Carga la sesion de inferencia ONNX Runtime y los metadatos del
        JSON de etiquetas
        """
        try:
            sess_options = _ort.SessionOptions()
            sess_options.graph_optimization_level = (
                _ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            self._session    = _ort.InferenceSession(ruta_onnx, sess_options)
            self._input_name = self._session.get_inputs()[0].name

            with open(ruta_labels, "r", encoding="utf-8") as f:
                meta = json.load(f)

            # idx_to_class puede ser {"0": "Apple", "1": "Banana", ...}
            idx_to_class = meta.get("idx_to_class", {})
            self._etiquetas   = [idx_to_class.get(str(i), "") for i in range(len(idx_to_class))]
            self._clases_dict = CLASES_FRUITS360
            
            self._preprocessing = meta.get("preprocessing", "imagenet")
            self._motor = "onnx"

            logger.info(
                "DetectorFrescos [ONNX] listo. Clases=%d val_acc=%.1f%%",
                len(self._etiquetas),
                meta.get("val_acc", 0.0) * 100,
            )

        except Exception as exc:
            print(f"[DetectorFrescos] ERROR: no fue posible cargar el modelo ONNX: {exc}")
            self._motor = None

    def detectar(self, frame) -> "dict | None":
        """
        Clasifica el frame y devuelve el producto fresco identificado
        si la confianza supera el umbral
        """
        if self._motor is None:
            return None

        probabilidades = self._inferir_onnx(frame)

        if probabilidades is None:
            return None

        top_idx  = int(np.argmax(probabilidades))
        top_conf = float(probabilidades[top_idx])
        etiqueta = self._etiquetas[top_idx] if top_idx < len(self._etiquetas) else ""

        # Top-3 siempre visible en consola para depuración
        top3_idx = np.argsort(probabilidades)[::-1][:3]
        top3 = [(self._etiquetas[i] if i < len(self._etiquetas) else "?",
                 float(probabilidades[i])) for i in top3_idx]
        print(f"  [NN] top3: {top3[0][0]} {top3[0][1]:.1%} | "
              f"{top3[1][0]} {top3[1][1]:.1%} | {top3[2][0]} {top3[2][1]:.1%}"
              f"  (umbral={self.CONFIANZA_MINIMA:.0%})")

        if top_conf < self.CONFIANZA_MINIMA:
            return None

        producto = self._buscar_fresco(etiqueta, self._clases_dict)
        if producto is None:
            return None

        barcode_id, nombre = producto
        return {
            "barcode": barcode_id,
            "productName": nombre,
            "detectionMethod": "IMAGE",
            "confidence": round(top_conf, 3),
        }


    def _inferir_onnx(self, frame):
        """
        Preprocesa el ROI y ejecuta el modelo ONNX
        """
        try:
            self.frame_debug = cv2.resize(frame, self.INPUT_SIZE)
            img = cv2.cvtColor(self.frame_debug, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32) / 255.0
            if self._preprocessing != 'divide_255':
                img = (img - _IMAGENET_MEAN) / _IMAGENET_STD
            tensor = np.expand_dims(img.transpose(2, 0, 1), axis=0)

            salida = self._session.run(None, {self._input_name: tensor})[0][0]

            if salida.max() > 1.0 or salida.min() < 0.0:
                exp    = np.exp(salida - salida.max())
                salida = exp / exp.sum()
            return salida

        except Exception as exc:
            logger.error("Error durante inferencia ONNX: %s", exc)
            return None


    @staticmethod
    def _buscar_fresco(etiqueta: str, clases: dict):
        """
        Busca palabras clave de la etiqueta del modelo en el diccionario
        de productos frescos
        """
        etiqueta_lower = etiqueta.lower()
        for clave in sorted(clases, key=len, reverse=True):
            if clave in etiqueta_lower:
                return clases[clave]
        return None
