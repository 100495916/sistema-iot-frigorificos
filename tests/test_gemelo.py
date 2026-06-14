"""
Pruebas unitarias de la lógica determinista del gemelo digital

9 tests — Nivel 1 del plan de pruebas (PU)
"""

import pytest


try:
    import gemelo_digital as gd
    from hardware.event import EventType
    GEMELO_DISPONIBLE = True
except Exception as exc:
    GEMELO_DISPONIBLE = False
    _IMPORT_ERROR = str(exc)

pytestmark = pytest.mark.skipif(
    not GEMELO_DISPONIBLE,
    reason=f"No se pudo importar gemelo_digital: {'' if GEMELO_DISPONIBLE else _IMPORT_ERROR}",
)

# # Test de _perfil_nevera
def test_perfil_mismo_id_es_deterministico():
    """El mismo FRIDGE_ID siempre genera el mismo perfil."""
    perfil_a = gd._perfil_nevera("nevera_prueba")
    perfil_b = gd._perfil_nevera("nevera_prueba")
    nombres_a = [p["nombre"] for p in perfil_a["productos"]]
    nombres_b = [p["nombre"] for p in perfil_b["productos"]]
    assert nombres_a == nombres_b

def test_perfil_ids_distintos_generan_perfiles_distintos():
    """Neveras distintas tienen productos distintos (al menos en parte)."""
    perfil_1 = gd._perfil_nevera("nevera_AAA")
    perfil_2 = gd._perfil_nevera("nevera_ZZZ")
    barcodes_1 = {p["barcode"] for p in perfil_1["productos"]}
    barcodes_2 = {p["barcode"] for p in perfil_2["productos"]}
    # Con semillas distintas es altamente improbable que coincidan exactamente
    assert barcodes_1 != barcodes_2

def test_perfil_tiene_campos_requeridos():
    perfil = gd._perfil_nevera("nevera_test")
    assert "productos" in perfil
    assert "stock_repo" in perfil
    assert "prob_alarma" in perfil
    assert "intervalo_ciclo_seg" in perfil

def test_perfil_cantidad_productos_dentro_de_rango():
    """Entre 5 y 10 productos: 4–7 envasados + 1–3 frescos."""
    perfil = gd._perfil_nevera("nevera_rango")
    assert 5 <= len(perfil["productos"]) <= 10

def test_perfil_prob_alarma_en_rango():
    perfil = gd._perfil_nevera("nevera_alarma")
    assert 0.10 <= perfil["prob_alarma"] <= 0.30


# # Test de productos_con_stock
def test_productos_con_stock_filtra_agotados():
    inventario = {
        gd.CATALOGO_ENVASADOS[0]["barcode"]: 0,
        gd.CATALOGO_ENVASADOS[1]["barcode"]: 3,
    }
    resultado = gd.productos_con_stock(gd.CATALOGO_ENVASADOS, inventario)
    barcodes = [p["barcode"] for p in resultado]
    assert gd.CATALOGO_ENVASADOS[0]["barcode"] not in barcodes
    assert gd.CATALOGO_ENVASADOS[1]["barcode"] in barcodes

def test_productos_con_stock_vacio_devuelve_lista_vacia():
    inventario = {p["barcode"]: 0 for p in gd.CATALOGO_ENVASADOS}
    assert gd.productos_con_stock(gd.CATALOGO_ENVASADOS, inventario) == []

def test_productos_con_stock_todos_disponibles():
    inventario = {p["barcode"]: 5 for p in gd.CATALOGO_ENVASADOS}
    resultado = gd.productos_con_stock(gd.CATALOGO_ENVASADOS, inventario)
    assert len(resultado) == len(gd.CATALOGO_ENVASADOS)


# # Test de crear_evento_producto
def test_crear_evento_producto_campos_requeridos():
    producto = gd.CATALOGO_ENVASADOS[0]
    evento = gd.crear_evento_producto(EventType.PRODUCT_ADDED, producto, 2)

    assert evento.fridge_id == gd.FRIDGE_ID
    assert evento.type == EventType.PRODUCT_ADDED
    assert evento.payload["barcode"] == producto["barcode"]
    assert evento.payload["cantidad"] == 2
    assert evento.event_id is not None
    assert evento.ts is not None
