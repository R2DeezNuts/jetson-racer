# Jetson Racer

Proyecto académico de percepción y control para un vehículo autónomo basado en Jetson. El sistema conecta la segmentación de imágenes con las órdenes de dirección y aceleración para que el vehículo siga el circuito.

Implementé la segmentación semántica e integré su salida con el control del vehículo, trabajando con Python y PyTorch. Puedes ver la plataforma física en la [demostración](https://youtu.be/iftXwQ2Pxf0).

## Código y documentación

La carpeta [socket_vision/](socket_vision/) contiene la comunicación entre el portátil y la Jetson, la recepción de vídeo y el control.

- [Conexión y lanzamiento del sistema](socket_vision/conexion/README.md).
- [Procesos de la Jetson](socket_vision/jetson/README.md).
- [Cliente de control](socket_vision/control/README.md).
- [Presentación del proyecto](presentacion/Presentaci%C3%B3nTFM-1.pdf).

[Volver al portfolio](https://r2deeznuts.github.io/)
