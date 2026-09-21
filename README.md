# MineHost

Gestor local de servidores Minecraft con interfaz gráfica. Sin dependencias: solo Python estándar.

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-windows-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

## Estado

| Tipo    | Soporte |
|---------|---------|
| Purpur  | ✅      |
| Paper   | 🔜      |
| Vanilla | 🔜      |
| Forge / Fabric | 🔜 |

## Uso

**Opción A — instalador (recomendado):** descarga `MineHost-Setup-*.exe` desde
[Releases](https://github.com/4DRI4N-OFF/minehost/releases). Asistente de
instalación, acceso directo y desinstalador incluidos. No requiere Python.

**Opción B — portable:** descarga `MineHost.exe` y ejecútalo directamente.

**Opción B — desde código:**

```bash
python minehost.py
```

1. Elige versión → **Actualizar**
2. Acepta el EULA → **Guardar config**
3. **▶ Iniciar** → `localhost:25565`

## Funciones

- Descarga automática del servidor desde la API oficial
- Detección del mejor Java instalado (Purpur 26.x requiere Java 25+)
- RAM, puerto y EULA configurables
- Consola en vivo con envío de comandos
- Exposición pública vía **ngrok** o **Playit** (juega con amigos sin abrir puertos)

## Amigos por internet (Playit)

1. Inicia el servidor, espera al `Done`
2. Pulsa **🚀 Playit**, reclama el agente en el link mostrado
3. Crea un túnel **Minecraft Java** → puerto `25565`
4. Comparte la dirección generada

## Desarrollo

```
minehost.py   # app (Tkinter, stdlib)
```

## Licencia

MIT
