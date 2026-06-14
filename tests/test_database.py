"""
Pruebas unitarias de los métodos auxiliares de conversión y validación de
la clase Database

11 tests — Nivel 1 del plan de pruebas (PU)
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def db():
    """
    Instancia de Database creada para evitar que el constructor intente c
    onectar con MongoDB Atlas
    """
    with patch("backend.database.MongoClient"):
        from backend.database import Database
        instance = Database.__new__(Database)
    return instance

# Test de to_positive_int
def test_to_positive_int_valor_valido(db):
    assert db.to_positive_int(5, 0) == 5

def test_to_positive_int_negativo_devuelve_default(db):
    assert db.to_positive_int(-3, 10) == 10

def test_to_positive_int_string_invalido_devuelve_default(db):
    assert db.to_positive_int("abc", 7) == 7

def test_to_positive_int_none_devuelve_default(db):
    assert db.to_positive_int(None, 4) == 4

# Test de to_bool
def test_to_bool_string_true(db):
    assert db.to_bool("true") is True

def test_to_bool_string_false(db):
    assert db.to_bool("false") is False

def test_to_bool_si(db):
    assert db.to_bool("si") is True

def test_to_bool_none_devuelve_default(db):
    assert db.to_bool(None, default=True) is True


# # Test de is_unknown_product_name
def test_is_unknown_none(db):
    assert db.is_unknown_product_name(None) is True

def test_is_unknown_prefijo(db):
    assert db.is_unknown_product_name("UNKNOWN_5449000000996") is True

def test_is_unknown_nombre_real(db):
    assert db.is_unknown_product_name("Leche Entera") is False
