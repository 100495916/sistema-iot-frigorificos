"""
Pruebas unitarias del servicio de inventario

17 tests — Nivel 1 del plan de pruebas (PU)
"""

import pytest
from unittest.mock import MagicMock

from backend.services.inventory_sync_service import TelemetryInventorySyncService


@pytest.fixture
def svc():
    """
    Instancia del servicio con ThingsBoard y MongoDB sustituidos por mocks
    """
    return TelemetryInventorySyncService(
        tb_client=MagicMock(),
        database=MagicMock(),
    )



# # Test de parse_value
def test_parse_value_dict_string(svc):
    assert svc.parse_value('{"barcode": "123", "cantidad": 2}') == {"barcode": "123", "cantidad": 2}

def test_parse_value_string_invalido(svc):
    assert svc.parse_value("no es json") == "no es json"

def test_parse_value_no_string(svc):
    assert svc.parse_value(42) == 42

# Test de build_events
def test_build_events_mismo_ts_se_fusionan(svc):
    telemetry = {
        "eventType": [{"ts": 1000, "value": "PRODUCT_ADDED"}],
        "fridgeId":  [{"ts": 1000, "value": "nevera_01"}],
    }
    events = svc.build_events(telemetry)
    assert len(events) == 1
    assert events[0]["eventType"] == "PRODUCT_ADDED"
    assert events[0]["fridgeId"] == "nevera_01"

def test_build_events_ts_distintos_generan_eventos_distintos(svc):
    telemetry = {
        "eventType": [
            {"ts": 1000, "value": "PRODUCT_ADDED"},
            {"ts": 2000, "value": "PRODUCT_REMOVE"},
        ],
    }
    events = svc.build_events(telemetry)
    assert len(events) == 2

# Test de rebuild_inventory
def _evento(event_type, barcode=None, cantidad=None, fridge_id="fridge_01"):
    """
    Constructor mínimo de evento para los tests de rebuild_inventory
    """
    ev = {"fridgeId": fridge_id, "eventType": event_type, "eventPayload": {}}
    if barcode:
        ev["eventPayload"]["barcode"] = barcode
    if cantidad is not None:
        ev["eventPayload"]["cantidad"] = cantidad
    return ev

def test_rebuild_product_added_crea_item(svc):
    events = [_evento("PRODUCT_ADDED", "ABC", 3)]
    resultado = svc.rebuild_inventory(events)
    assert len(resultado["items"]) == 1
    assert resultado["items"][0]["qty"] == 3

def test_rebuild_product_added_acumula_cantidad(svc):
    events = [
        _evento("PRODUCT_ADDED", "ABC", 3),
        _evento("PRODUCT_ADDED", "ABC", 2),
    ]
    resultado = svc.rebuild_inventory(events)
    assert resultado["items"][0]["qty"] == 5

def test_rebuild_product_remove_decrementa(svc):
    events = [
        _evento("PRODUCT_ADDED", "ABC", 5),
        _evento("PRODUCT_REMOVE", "ABC", 2),
    ]
    resultado = svc.rebuild_inventory(events)
    assert resultado["items"][0]["qty"] == 3

def test_rebuild_product_remove_elimina_item_en_cero(svc):
    events = [
        _evento("PRODUCT_ADDED", "ABC", 2),
        _evento("PRODUCT_REMOVE", "ABC", 2),
    ]
    resultado = svc.rebuild_inventory(events)
    assert len(resultado["items"]) == 0

def test_rebuild_product_remove_exceso_elimina_item(svc):
    """
    PRODUCT_REMOVE con qty > stock. No genera negativo, el item desaparece
    """
    events = [
        _evento("PRODUCT_ADDED", "ABC", 1),
        _evento("PRODUCT_REMOVE", "ABC", 10),
    ]
    resultado = svc.rebuild_inventory(events)
    assert len(resultado["items"]) == 0

def test_rebuild_product_remove_sin_existir_ignorado(svc):
    events = [_evento("PRODUCT_REMOVE", "ABC", 3)]
    resultado = svc.rebuild_inventory(events)
    assert len(resultado["items"]) == 0

def test_rebuild_cantidad_malformada_no_aborta(svc):
    """
    Un evento histórico con `cantidad` corrupta se ignora sin romper el rebuild
    """
    events = [
        _evento("PRODUCT_ADDED", "ABC", 3),
        _evento("PRODUCT_ADDED", "XXX", "dos"),
        _evento("PRODUCT_ADDED", "YYY", "2.5"),
        _evento("PRODUCT_REMOVE", "ABC", 1),
    ]
    resultado = svc.rebuild_inventory(events)
    assert len(resultado["items"]) == 1
    assert resultado["items"][0]["barcode"] == "ABC"
    assert resultado["items"][0]["qty"] == 2
    assert resultado["ignoredEvents"] == 2

def test_rebuild_multiples_productos(svc):
    events = [
        _evento("PRODUCT_ADDED", "AAA", 4),
        _evento("PRODUCT_ADDED", "BBB", 2),
        _evento("PRODUCT_REMOVE", "AAA", 4),
    ]
    resultado = svc.rebuild_inventory(events)
    barcodes = [i["barcode"] for i in resultado["items"]]
    assert "BBB" in barcodes
    assert "AAA" not in barcodes



# # Test de normalize_individual_event
def test_normalize_payload_plano(svc):
    raw = {
        "fridgeId":    "fridge_01",
        "eventType":   "PRODUCT_ADDED",
        "eventPayload": {"barcode": "123", "cantidad": 1},
    }
    resultado = svc.normalize_individual_event(raw)
    assert resultado["fridgeId"] == "fridge_01"
    assert resultado["eventType"] == "PRODUCT_ADDED"

def test_normalize_payload_envuelto_en_msg(svc):
    raw = {
        "msg": {
            "fridgeId":    "fridge_02",
            "eventType":   "PRODUCT_REMOVE",
            "eventPayload": {},
        }
    }
    resultado = svc.normalize_individual_event(raw)
    assert resultado["fridgeId"] == "fridge_02"

def test_normalize_sin_fridge_id_lanza_error(svc):
    raw = {"eventType": "PRODUCT_ADDED"}
    with pytest.raises(ValueError, match="fridgeId"):
        svc.normalize_individual_event(raw)

def test_normalize_event_payload_como_string_se_parsea(svc):
    raw = {
        "fridgeId":    "fridge_01",
        "eventType":   "PRODUCT_ADDED",
        "eventPayload": '{"barcode": "999", "cantidad": 2}',
    }
    resultado = svc.normalize_individual_event(raw)
    assert isinstance(resultado["eventPayload"], dict)
    assert resultado["eventPayload"]["barcode"] == "999"
