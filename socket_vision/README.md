# Socket Vision

Codigo usado para conectar el coche con el portatil, procesar la vision en
tiempo real y mandar comandos a la Jetson.

## Como lanzar el programa

Desde la carpeta `ENTREGA_TFM/` ejecuta:

```bash
bash socket_vision/conexion/scripts/main.sh
```

Ese comando sincroniza con la Jetson y arranca el flujo completo: video,
vision, control automatico y control manual.

## Flujo general

- `Jetson -> portatil`: la Jetson captura la camara y envia video.
- `portatil`: recibe el video, ejecuta vision y calcula direccion/velocidad.
- `portatil -> Jetson`: el portatil envia comandos de control.
- `Jetson`: aplica `steering` y `throttle` al coche.

## Bloques principales de `socket_vision`

- `conexion`: comunicacion entre portatil y Jetson, scripts de arranque y sincronizacion.
- `vision`: inferencia del modelo, procesado de mascaras y decision automatica.
- `control`: cliente de control manual y protocolo de comandos.
- `jetson`: procesos que corren en la Jetson (`sender` y `control_server`).
- `models`: modelo ONNX usado para segmentar circuito y cajas.

## Archivos clave

- `global_config.json`: configuracion general de IP, puertos y rutas.
- `config_loader.py`: carga la configuracion global y la combina con la de cada modulo.
- `conexion/scripts/main.sh`: script principal para lanzar el flujo completo.
- `conexion/receiver.py`: recibe video en el portatil, ejecuta vision y envia comandos.
- `vision/perception/line_segmentation.py`: carga el ONNX y calcula mascaras.
- `vision/runtime/autonomy.py`: convierte la informacion visual en `steering` y `throttle`.
- `jetson/sender.py`: captura la camara en la Jetson y envia video.
- `jetson/control_server.py`: recibe comandos y mueve el coche.

## Mas informacion

- `conexion/README.md`: comunicacion y scripts.
- `vision/README.md`: percepcion e inferencia.
- `control/README.md`: mando manual.
- `jetson/README.md`: procesos remotos de la Jetson.
