# Este archivo ha sido refactorizado. Toda la logica vive ahora en:
#
#   backend/app.py                               -- create_app(), lifespan, CORS, routers
#   backend/config.py                            -- variables de entorno
#   backend/clients/thingsboard_client.py        -- ThingsBoardApiRestClient
#   backend/services/inventory_sync_service.py   -- TelemetryInventorySyncService
#   backend/services/startup_sync_service.py     -- build_inventory_service, run_startup_inventory_rebuild
#   backend/routes/inventory_routes.py           -- GET fridges, inventario, eventos
#   backend/routes/shopping_list_routes.py       -- reglas, lista compra, evaluar, pedir, completar
#   backend/routes/thingsboard_routes.py         -- POST thingsboard/individual
#
# Este archivo puede borrarse una vez verificado que el backend arranca correctamente.
