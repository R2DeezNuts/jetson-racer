# Conexion

Bloque de comunicacion entre portatil y Jetson para el flujo principal.

## Config

- `config/default_config.json`: red y stream de video (IP, puertos, UDP/TCP, JPEG, FPS).

## Codigo

- `protocol.py`: framing de video para TCP y UDP.
- `receiver.py`: receptor local de video + vision + envio de comandos auto a Jetson.

## Scripts del flujo principal

- `scripts/main.sh`: entrada principal. Sincroniza y abre 2 terminales (vision y control).
- `scripts/launch_all_from_laptop.sh`: arranca sender y control_server en Jetson, luego receiver en portatil.
- `scripts/run_control_client.sh`: abre cliente manual y asegura control_server remoto.
- `scripts/sync_to_jetson.sh`: sincronizacion minima de runtime hacia Jetson.
- `scripts/start_remote_control_server.sh`: arranque puntual de control_server remoto.
- `scripts/session_terminal.sh`: control de sesion de terminales abiertas por `main.sh`.
- `scripts/cleanup_remote.sh`: parada remota final al cerrar la sesion.
- `scripts/load_global_env.sh`: carga valores desde `global_config.json`.

## Lanzamiento recomendado

Desde `TFM/`:

```bash
bash socket_vision/conexion/scripts/main.sh
```
