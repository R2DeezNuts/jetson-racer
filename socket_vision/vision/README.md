# Vision

Bloque de percepcion y decision del flujo principal.

## Config

- `config/default_config.json`: parametros de inferencia, umbrales de mascara, ROI, y UI de overlay.

## Runtime

- `runtime/autonomy.py`: convierte `lane_info` en comando auto (`steering` + `throttle`).
- `runtime/vision.py`: dibuja overlay final sobre la ventana principal (mascaras, estado, latencia, FPS).

## Perception

- `perception/pipeline.py`: entrada unica del pipeline de percepcion activo.
- `perception/line_segmentation.py`: carga el ONNX, decodifica canales (circuito/cajas), endurece mascara de circuito y calcula centro.

## Modelo

- `../models/line_segmentation/line_model.onnx`: modelo cargado en runtime.
- `../models/line_segmentation/line_model.onnx.data`: pesos externos del ONNX.

## Dependencias

- `requirements.txt`: dependencias minimas de runtime para vision.
