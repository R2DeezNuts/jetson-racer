# Jetson

Procesos remotos usados por el flujo principal.

## Procesos

- `socket_vision.jetson.sender`: captura camara y envia video al portatil.
- `socket_vision.jetson.control_server`: recibe comandos y aplica `steering`/`throttle`.

## Flujo

- video: `Jetson -> portatil`
- control: `portatil -> Jetson`

## Archivos clave

- `sender.py`
- `control_server.py`
- `../conexion/config/default_config.json`
- `../control/config/default_config.json`
- `../control/assets/sounds/`

## Scripts relevantes

- `../conexion/scripts/main.sh`
- `../conexion/scripts/launch_all_from_laptop.sh`
- `../conexion/scripts/sync_to_jetson.sh`
- `../conexion/scripts/start_remote_control_server.sh`
