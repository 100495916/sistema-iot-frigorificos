import cv2

try:
    _cv_detector = cv2.barcode.BarcodeDetector()

    _cv_detector.setDownsamplingThreshold(1920)

    _cv_detector.setGradientThreshold(32)

    _cv_detector.setDetectorScales([0.01, 0.02, 0.03, 0.05, 0.06, 0.08])
    _CV_BARCODE_OK = True
    
except AttributeError:
    _CV_BARCODE_OK = False


class _Resultado:
    def __init__(self, data: bytes, rect=(0, 0, 0, 0)):
        """
        Guarda el contenido decodificado del barcode (bytes) y el
        rectangulo (x, y, ancho, alto) donde se detecto en el frame
        """
        self.data = data
        self.rect = rect


def _decodificar_cv(frame, escala: float = 1.0):
    """
    Ejecuta el detector cv2.barcode sobre un frame
    """
    try:
        ok, infos, types, corners = _cv_detector.detectAndDecodeWithType(frame)
        if ok:
            resultados = []
            for dato, pts in zip(infos, corners if corners is not None else []):
                if dato:
                    rect = (0, 0, 0, 0)
                    if pts is not None and len(pts) > 0:
                        xs = (pts[:, 0] * escala).astype(int)
                        ys = (pts[:, 1] * escala).astype(int)
                        rect = (int(xs.min()), int(ys.min()),
                                int(xs.max() - xs.min()), int(ys.max() - ys.min()))
                    resultados.append(_Resultado(dato.encode("utf-8"), rect))
            return resultados
    except Exception:
        pass
    return []


def _preprocesar(frame):
    """Escala de grises + CLAHE + sharpening"""
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gris = clahe.apply(gris)
    blur = cv2.GaussianBlur(gris, (0, 0), 1)
    return cv2.addWeighted(gris, 1.5, blur, -0.5, 0)


def intentar_decodificar_avanzado(frame, roi=None):
    """Prueba 2 variantes en orden, calculando la segunda solo si la primera falla
    """
    if not _CV_BARCODE_OK:
        return [], None

    if roi is not None:
        x1, y1, x2, y2 = roi
        frame = frame[y1:y2, x1:x2]
        if frame.size == 0:
            return [], None

    def _variantes():
        yield frame, "Color", 1.0
        yield _preprocesar(frame), "Gris+CLAHE", 1.0
        up = cv2.resize(frame, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        yield up, "Upscaled", 0.5

    for img, metodo, escala in _variantes():
        codigos = _decodificar_cv(img, escala=escala)
        if codigos:
            return codigos, metodo

    return [], None

