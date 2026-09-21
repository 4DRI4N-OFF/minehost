# Purpur Server Manager

Herramienta con GUI (Tkinter) para hostear un servidor de Minecraft **Purpur** de manera local en Windows. Sin dependencias externas: solo Python estándar.

## Funciones

- Descarga Purpur (última build) desde la API oficial con selector de versión
- Detección automática del mejor Java instalado (Purpur 26.x exige **Java 25+**)
- Configuración de RAM mín/máx, puerto y EULA
- Consola en vivo con envío de comandos (`stop`, `whitelist add ...`, etc.)
- Botón **🌐 Túnel público (ngrok)** y **🚀 Playit** para jugar con amigos sin port forwarding
- Muestra tu IP local para conexión en LAN (`localhost:25565`)

## Requisitos

- Python 3.10+ (incluye Tkinter en Windows)
- Java 25+ ([Temurin](https://adoptium.net)) para Purpur 26.x
- Opcional: [ngrok](https://ngrok.com/download) o [Playit](https://playit.gg) para exponer el servidor

## Uso

```bash
python minecraft_server_manager.py
```

1. Espera a que carguen las versiones → **Actualizar Purpur**
2. Marca **Acepto EULA** → **Guardar config**
3. **▶ Iniciar** → conéctate a `localhost:25565`

## Jugar con amigos (Playit)

1. Inicia el servidor y espera al `Done`
2. Pulsa **🚀 Playit** → abre el link `playit.gg/claim/...` y reclama el agente
3. En playit.gg crea un túnel **Minecraft Java** con puerto local `25565`
4. Comparte la dirección (ej. `algo.mc.ply.gg`)

## Estructura generada

```
server/          # se crea al lado del script: purpur.jar, world, plugins, logs...
manager_config.json
```

## Licencia

MIT
