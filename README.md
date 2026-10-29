# Socket Vision (TFM)

## Como lanzar el programa

Desde la carpeta `TFM/` ejecuta:

```bash
bash socket_vision/conexion/scripts/main.sh
```

Ese comando sincroniza con la Jetson y arranca el flujo completo (video + control).

## Bloques principales de `socket_vision`

- `vision`: procesa el video, segmenta circuito/cajas y calcula el comando automatico.
- `control`: gestiona el control manual y el protocolo de comandos.
- `conexion`: conecta portatil y Jetson (stream de video, arranque remoto y orquestacion).
- `jetson`: procesos que corren en la Jetson (`sender` y `control_server`).
