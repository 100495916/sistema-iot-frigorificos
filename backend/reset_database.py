import os

from dotenv import load_dotenv
from pymongo import MongoClient


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

# Cogemos las variables directamente desde el .env
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "iot_tfg")

def reset_database():
    """
    Elimina las cinco colecciones del sistema en MongoDB para dejar la
    base de datos limpia para poder probar
    """
    print("Conectando a MongoDB...")

    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]

    print("Eliminando colecciones de la arquitectura actual...")

    # Colecciones usadas por el backend
    db.drop_collection("inventario")
    db.drop_collection("eventos_procesados")
    db.drop_collection("productos_cache")
    db.drop_collection("lista_compra")
    db.drop_collection("reglas_lista_compra")

    print("Colecciones eliminadas correctamente.")


if __name__ == "__main__":
    confirm = input("Seguro que quieres borrar inventario, eventos_procesados y productos_cache? (yes/no): ")

    if confirm.lower() == "yes":
        reset_database()
    else:
        print("Operacion cancelada.")
