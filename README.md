# TFG — Sistema IoT para Frigoríficos

Sistema IoT de gestión de inventario para frigoríficos. Detecta productos mediante visión artificial (cámara + modelo ONNX) o simulación, publica eventos MQTT a ThingsBoard y mantiene el inventario actualizado en MongoDB.

---

## Arquitectura

```
Edge (Gemelo Digital / Raspberry Pi)
        │  MQTT
        ▼
ThingsBoard CE  →  Rule Chain  →  REST POST
        │  HTTP
        ▼
Backend FastAPI  →  MongoDB Atlas
        │
        ▼
Dashboard (HTML/JS)
```

| Componente | Tecnología | Dónde corre |
|---|---|---|
| Backend | FastAPI + Python | GKE (`tfg-cluster-servicios`) |
| Dashboard | HTML/CSS/JS estático | GKE (`tfg-cluster-servicios`) |
| Gemelo digital | Python + Docker | GKE (`tfg-cluster-edge`) |
| ThingsBoard CE | X | VM GCP `34.175.184.158:8080` |
| MongoDB | Atlas | Siempre online |

---

## Estructura del repositorio

```
tfg-iot-frigorifico/
├── backend/                      # API FastAPI
│   ├── main.py                   # Punto de entrada
│   ├── app.py                    # Configuracion FastAPI, CORS, routers
│   ├── config.py                 # Variables de entorno
│   ├── database.py               # Lógica MongoDB
│   ├── clients/
│   │   └── thingsboard_client.py
│   ├── routes/
│   │   ├── inventory_routes.py
│   │   ├── shopping_list_routes.py
│   │   └── thingsboard_routes.py
│   ├── services/
│   │   ├── inventory_sync_service.py
│   │   └── startup_sync_service.py
│   ├── requirements.txt          # Dependencias solo del backend
│   ├── Dockerfile
│   └── docker-compose.yml        # Para desarrollo local
│  
├── dashboard/                    # Frontend estático
│   ├── config.js               
│   ├── js/                       # Codigo en JavaScript para el funcionamiento del Frontend
│   ├── index.html
│   ├── inventory.html
│   ├── historial.html
│   ├── reglas.html
│   ├── lista-compra.html
│   └── configuracion.html
│
├── edge/                         # Código del dispositivo edge
│   ├── gemelo_digital.py         # Simulador de nevera
│   ├── test_camara.py            # Prueba la cámara en vivo
│   ├── docker-compose.yml        # Levanta neveras en local
│   ├── hardware/
│   │   ├── camara.py             # Lector de barcode con cv2.barcode
│   │   ├── camara_fisica.py      # Pipeline completo: YOLO + barcode + frescos
│   │   ├── detector_frescos.py   # Clasificador EfficientNet B0
│   │   ├── detector_objeto.py    # Localizador YOLOv8n
│   │   ├── event.py              # Clase Event y EventType
│   │   ├── buffer.py             # Cola de eventos pendientes
│   │   └── modelos/            
│   │       ├── modelo_frutas.onnx
│   │       ├── modelo_frutas_labels.json
│   │       └── yolov8n.onnx
│   └── requirements.txt          # Dependencias edge (Windows)
│
├── k8s/                          # Manifiestos Kubernetes
│   ├── backend/
│   │   ├── configmap.yaml
│   │   ├── secret.yaml.template  # Copiar a secret.yaml y rellenar
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── dashboard/
│   │   ├── configmap.yaml
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── edge/
│       ├── configmap.yaml        # Variables del gemelo (host TB, puertos)
│       ├── secret.yaml.template  # Copiar a secret.yaml y rellenar
│       ├── statefulset.yaml      # 20 réplicas
│       └── service-headless.yaml
│
├── tests/
    ├── postman/                  # JSON con las colecciones de los test para la API             
│   ├── conftest.py               # Tests unitarios (pytest)
│   ├── test_inventario.py     
│   ├── test_database.py
│   └── test_gemelo.py
│
│
├── tfg_entrenamiento_modelo.ipynb  # Notebook de entrenamiento EfficientNet B0
└── requirements.txt                # Dependencias compartidas (edge + backend)

```

---

## Arranque local

### ThingsBoard
```powershell
cd backend
docker compose up -d --build
```
```

### Backend con Docker
```powershell
cd backend
docker compose up -d --build
```

### Dashboard
```powershell
cd dashboard
docker compose up -d --build
# http://localhost:8085
```

### Gemelo digital (simulación local)
```powershell
cd edge
docker compose up -d --build
# Levanta Nevera_Docker_001 y Nevera_Docker_002
```

---

## Despliegue en GKE

### Servicios
```bash
# Crear el cluser

gcloud container clusters get-credentials tfg-cluster-servicios --zone europe-southwest1-a

kubectl create secret generic backend-secret \
  --from-literal=MONGODB_URI="" \
  --from-literal=TB_USERNAME="" \
  --from-literal=TB_PASSWORD="" \
  --from-literal=TB_API_KEY=""
  
kubectl apply -f k8s/backend/configmap.yaml
kubectl apply -f k8s/backend/deployment.yaml
kubectl apply -f k8s/backend/service.yaml

kubectl apply -f k8s/dashboard/configmap.yaml
kubectl apply -f k8s/dashboard/deployment.yaml
kubectl apply -f k8s/dashboard/service.yaml

kubectl get pods
```

### Gemelo digital (cluster edge)
```bash
# Crear el cluser

gcloud container clusters get-credentials tfg-cluster-edge --zone europe-southwest1-a

kubectl create secret generic edge-secret \
  --from-literal=PROVISION_KEY="" \
  --from-literal=PROVISION_SECRET=""
  
kubectl apply -f k8s/edge/configmap.yaml
kubectl apply -f k8s/edge/service-headless.yaml
kubectl apply -f k8s/edge/statefulset.yaml

kubectl get pods
```

---

## Tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest tests\ -v

# 37 tests, sin conexión a MongoDB ni ThingsBoard.
```

### Test de cámara
```bash
cd edge
python test_camara.py

# Controles: [q] salir [s] captura [a] ambos [b] barcode [f] frescos
```

---
