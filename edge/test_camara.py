"""
Script de prueba de la camara en tiempo real.
NO requiere ThingsBoard ni MQTT: solo la camara y las dependencias de vision.

Controles:
    q  — salir
    s  — guardar captura de pantalla
    a  — detectar ambos
    b  — solo barcode
    f  — solo frescos
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import cv2
except ImportError:
    print("ERROR: OpenCV no instalado. Ejecuta:  pip install opencv-python")
    sys.exit(1)

from hardware.camara_fisica import CamaraFisica


def test_camara_viva(camera_index: int, usar_frescos: bool):
    """
    Abre la camara en vivo con preview y ejecuta el pipeline completo de
    deteccion
    """
    print("-" * 40)
    print("TEST CAMARA EN VIVO")
    print("-" * 40)
    
    print(f"  Camara index : {camera_index}")
    print(f"  Frescos (NN) : {'SI' if usar_frescos else 'NO'}")
    print()
    if usar_frescos:
        print(" Cargando detector de frescos (modelo ONNX)...")
    print("  Controles: [q] salir  [s] captura")
    print()

    camara = CamaraFisica(
        camera_index=camera_index,
        cooldown_seg=3.0,
        frames_confirmacion=5,
        mostrar_preview=True,
        usar_frescos=usar_frescos,
    )

    camara.iniciar()
    _detector_frescos_original = camara._detector_frescos
    print("  Camara lista.\n")
    print("  Modo actual: AMBOS  [a] ambos  [b] solo barcode  [f] solo frescos  [q] salir\n")

    capturas = 0

    try:
        while True:
            detectado = camara.leer_frame()

            if detectado:
                _imprimir_deteccion(detectado)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord("q"):
                break
            elif tecla == ord("s"):
                nombre = f"captura_{capturas:03d}.jpg"
                ret, frame = camara._cap.read()
                if ret:
                    cv2.imwrite(nombre, frame)
                    print(f"  [s] Captura guardada: {nombre}")
                    capturas += 1
            elif tecla == ord("a"):
                camara.usar_barcode = True
                camara._detector_frescos = _detector_frescos_original
                print("  Modo: AMBOS (barcode + frescos)")
            elif tecla == ord("b"):
                camara.usar_barcode = True
                camara._detector_frescos = None
                print("  Modo: solo BARCODE")
            elif tecla == ord("f"):
                camara.usar_barcode = False
                camara._detector_frescos = _detector_frescos_original
                print("  Modo: solo FRESCOS")

            try:
                if cv2.getWindowProperty("Frigorifico | Camara", cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break

    except KeyboardInterrupt:
        print("\n  Saliendo...")
    finally:
        camara.detener()


def _imprimir_deteccion(det: dict):
    """
    Imprime por consola una deteccion con formato uniforme
    """
    print("-" * 40)
    nombre = det.get("productName") or det["barcode"]
    metodo = det["detectionMethod"]
    barcode = det["barcode"]
    confianza = det["confidence"]
    icono = "[CAM]" if metodo == "BARCODE" else "[NN] "
    print(f"  {icono} {nombre}")
    print(f"         barcode   : {barcode}")
    print(f"         metodo    : {metodo}")
    print(f"         confianza : {confianza:.1%}")
    print("-" * 40)


def main():
    test_camara_viva(camera_index=0, usar_frescos=True)


if __name__ == "__main__":
    main()
