# Segmentacion de circuito y obstaculos para coche con Jetson Nano

Este proyecto esta pensado para hacer en el PC todo lo pesado:

1. Preparar el dataset.
2. Entrenar el modelo de segmentacion.
3. Probarlo con imagenes o video.
4. Exportarlo a ONNX.
5. Pasar a la Jetson Nano solo lo necesario para inferencia.

El modelo por defecto es una UNet pequena en PyTorch con dos salidas:

- canal 0: circuito, lineas o zona transitable
- canal 1: caja/obstaculo

Esto evita ejecutar dos modelos en la Jetson Nano. Es menos pesado que DeepLabv3+ con ResNet50 y tiene mas sentido para tiempo real.

## Estructura

```text
circuito_segmentation/
  data/
    train/
      images/   imagenes de entrenamiento
      track_masks/     mascaras del circuito
      obstacle_masks/  mascaras de cajas/obstaculos
    val/
      images/   imagenes de validacion
      track_masks/     mascaras del circuito
      obstacle_masks/  mascaras de cajas/obstaculos
    test/
      images/   imagenes sueltas para probar
  checkpoints/  modelos entrenados .pth
  exports/      modelos exportados .onnx
  outputs/      predicciones generadas
  src/          codigo
```

## Formato del dataset

Puedes trabajar de dos formas.

### Opcion mas comoda: notebook completo

Usa:

```text
notebooks/entrenamiento_completo_makesense.ipynb
```

Flujo:

1. Pon imagenes originales en `00_imagenes_para_makesense/`.
2. Etiqueta esas imagenes en MakeSense con `circuito` y `caja`.
3. Exporta COCO JSON como `01_export_makesense/anotaciones.json`.
4. Ejecuta el notebook completo.

El notebook genera:

```text
raw/images/
raw/track_masks/
raw/obstacle_masks/
data/train/
data/val/
checkpoints/best_model.pth
exports/circuit_unet.onnx
```

### Opcion recomendada: una sola carpeta raw

Pon todo aqui:

```text
raw/images/
raw/track_masks/
raw/obstacle_masks/
```

Luego genera automaticamente `train` y `val`:

```bash
python src/prepare_dataset.py --raw-dir raw --out-dir data --val-size 0.2
```

El script usa `scikit-learn` si esta instalado. Si no lo esta, usa una division aleatoria equivalente con Python.

Por defecto crea enlaces simbolicos para no duplicar archivos. Si prefieres copias reales:

```bash
python src/prepare_dataset.py --raw-dir raw --out-dir data --val-size 0.2 --copy
```

### Opcion manual

Tambien puedes colocar directamente los archivos en `data/train` y `data/val`.

Cada imagen debe tener dos mascaras con el mismo nombre base.

Ejemplo:

```text
data/train/images/frame_0001.jpg
data/train/track_masks/frame_0001.png
data/train/obstacle_masks/frame_0001.png
```

Cada mascara debe ser una imagen en escala de grises:

- `0`: fondo
- `255`: clase segmentada

Para `track_masks`, marca una de estas dos cosas:

- Segmentando las lineas negras: util para calcular los bordes.
- Segmentando la zona transitable: normalmente mas facil para conducir, porque el centro se calcula directamente sobre la zona valida.

Para `obstacle_masks`, marca solo la caja u obstaculo.

Si en una imagen no hay caja, crea igualmente una mascara completamente negra en `obstacle_masks`.

## Instalacion en el PC

```bash
cd circuito_segmentation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Si ya tienes PyTorch con CUDA instalado, puedes instalar solo:

```bash
pip install opencv-python pillow numpy tqdm matplotlib
```

## Entrenar

```bash
python src/train.py --data-dir data --epochs 40 --batch-size 8 --img-size 256
```

Por defecto se da mas peso a la caja/obstaculo porque suele ocupar pocos pixeles. Puedes ajustarlo asi:

```bash
python src/train.py --data-dir data --epochs 40 --obstacle-weight 3.0
```

El mejor modelo se guarda en:

```text
checkpoints/best_model.pth
```

## Probar con una imagen

```bash
python src/predict_image.py \
  --checkpoint checkpoints/best_model.pth \
  --image data/test/images/tu_imagen.jpg \
  --out outputs/prediccion.png
```

## Probar con video o camara en el PC

Con video:

```bash
python src/predict_video.py \
  --checkpoint checkpoints/best_model.pth \
  --source video.mp4 \
  --out outputs/video_segmentado.mp4
```

Con camara:

```bash
python src/predict_video.py --checkpoint checkpoints/best_model.pth --source 0
```

## Exportar a ONNX

```bash
python src/export_onnx.py \
  --checkpoint checkpoints/best_model.pth \
  --out exports/circuit_unet.onnx
```

## Llevar a Jetson Nano

Para la Nano copia como minimo:

```text
src/model.py
src/jetson_runtime.py
checkpoints/best_model.pth
```

O si vas a usar ONNX/TensorRT:

```text
exports/circuit_unet.onnx
```

El script `src/jetson_runtime.py` esta preparado como base para leer camara, segmentar y calcular un error de direccion. La parte de mandar ordenes al motor queda marcada como `TODO`, porque depende de tu driver/controlador.

## Logica de conduccion incluida

El runtime calcula:

- `track_error`: desplazamiento del circuito respecto al centro de la imagen.
- `obstacle_error`: posicion de la caja si aparece en la zona frontal.
- `steering`: mezcla de seguir circuito y esquivar obstaculo.

La parte importante esta en `compute_control()` dentro de `src/jetson_runtime.py`.
