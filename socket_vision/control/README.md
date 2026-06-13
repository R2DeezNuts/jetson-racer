# Control

Bloque de mando del coche para el flujo principal.

## Config

- `config/default_config.json`: ganancias, limites de steering/throttle, modos auto/manual y umbrales de evitacion.

## Codigo

- `protocol.py`: protocolo JSON por linea para comandos de control.
- `laptop_control_client.py`: cliente manual desde portatil (`w/a/d/s`, espacio, `q`).

## Recursos

- `assets/sounds/`: sonidos de acciones manuales.

## Relacion con Jetson

El servidor que aplica comandos al coche esta en:

- `../jetson/control_server.py`
