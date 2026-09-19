# ADR-0006: `MarkdownSink` es un puerto y `convert` escribe solo a través de él
Fecha: 2026-09-19   Estado: Aceptada

## Contexto
CLAUDE.md §3 lista tres puertos en `core/ports/`: `ExportSource`, `MarkdownSink` y `ProgressReporter`. Al cerrar M1 solo existía `ExportSource`. `usecases/convert.py` importaba directamente las funciones de `adapters/sink_filesystem.py` (`ensure_writable`, `write_memories`, `write_conversations`, `write_markdown`, `write_report`), así que:

- el caso de uso quedaba soldado al sistema de archivos: no se podía probar la orquestación sin escribir en disco;
- M3 necesita devolver el resultado como un `.zip` (`GET /exports/{id}/download`) y no había dónde enchufarlo sin duplicar `convert`;
- las funciones del adapter mezclaban **render** (llamaban a `render_memories` / `render_conversations`, es decir a Jinja2) con **escritura**. Un `ZipSink` que implementara esa misma interfaz habría tenido que saber de plantillas y de entidades de dominio para escribir bytes.

## Decisión
1. **`ports/sink.py` define `MarkdownSink` como un `Protocol` mínimo**, con lo único que `convert` necesita hoy:
   - `location: str` — dónde escribe, para poder decírselo al usuario (una ruta, el nombre de un zip…).
   - `ensure_writable(overwrite: bool = False) -> None` — comprobar ANTES de escribir el primer byte; lanza `OutputNotEmptyError` (spec 05 CA-3).
   - `write(path: str, content: str) -> None` — `path` es **relativa a la raíz del sink y en formato POSIX**; el contenido ya viene renderizado.

   No lleva `write_memories` / `write_conversations` / `write_report`: esos métodos obligarían a cada sink a conocer `Memory`, `Conversation`, `Environment` y `Inventory`. El puerto transporta texto; quién lo produce es `rendering/`.
2. **`adapters/sink_filesystem.py` expone `FilesystemSink`**, que implementa el puerto sobre una carpeta (UTF-8 y `\n` siempre, también en Windows). Las funciones sueltas `ensure_writable` y `write_text` siguen existiendo como cuerpo de los métodos; las que mezclaban render y escritura desaparecen.
3. **`convert(source, sink, …)` recibe el puerto**, no una ruta. El bucle `render → sink.write` vive en el caso de uso, que es donde se decide el orden. `ConvertResult.files` pasa a ser una tupla de rutas **relativas POSIX** (lo que el sink recibió) y `ConvertResult.destination` es `sink.location`: el resultado deja de hablar de `pathlib`, que es un detalle del sink de disco.
4. **Quien construye el sink concreto es la capa de entrada.** El CLI hace `FilesystemSink(salida)` y se lo pasa a `convert`; la API hará lo mismo en M3.

## `ProgressReporter`: todavía no
Se mantiene `ProgressCallback = Callable[[str, int], None]` en vez de crear el tercer puerto. Razón: hoy `convert` emite exactamente un evento (`(categoría, ítems hechos)`) y no hay un segundo consumidor con necesidades distintas. Un `Protocol` de un solo método sin argumentos por nombre no aporta nada sobre un `Callable` tipado, y `Callable` deja escribir el test con un `lambda`. Cuando la API necesite SSE (M3: `start`/`advance`/`finish`, total de ítems, cancelación) el callback se quedará corto y ese será el momento del puerto, con la forma que pida el consumidor real y no la que adivinemos ahora. CLAUDE.md §3 enumera el destino, no obliga a llegar en M1.

## Alternativas consideradas
- **`MarkdownSink` con los métodos gordos actuales** (`write_memories(memories, environment)`) — es el menor cambio, pero mete Jinja2 y el dominio dentro del puerto y convierte cada sink futuro en un segundo renderizador. Se descartó.
- **`convert(source, out: Path | MarkdownSink)`** — cómodo para quien llama, pero devuelve al caso de uso la responsabilidad de construir un adapter concreto, que es justo lo que este ADR quita. La comodidad vive en el CLI, que es quien ya sabe que el destino es una carpeta.
- **Dejar `Path` en `ConvertResult.files`** — obliga a todo sink a tener rutas de disco; un `ZipSink` no las tiene. Las rutas relativas POSIX son las que ya usa `rendering/` y las que valen en los tres destinos.

## Consecuencias
+ `convert` se prueba con un sink en memoria, sin tocar el disco (`packages/core/tests/test_convert.py::RecordingSink`).
+ M3 solo tiene que escribir `ZipSink` (dos métodos) para servir la descarga; `convert` no cambia.
+ `adapters/sink_filesystem.py` queda reducido a I/O de verdad, sin importar `rendering/`.
— Cambio incompatible en la API pública de `core`: `convert(source, out)` pasa a `convert(source, sink)` y desaparecen `write_memories`/`write_conversations`/`write_report`/`write_markdown` de `claude_export_md.__init__`. Nada está publicado todavía (`0.1.0`, sin release en PyPI), así que el coste es cero fuera del repo.
— Los nombres del árbol de salida (`_report/`, `summary.json`, `errors.jsonl`, `inventory.json`) se mudan de `adapters/sink_filesystem.py` a `rendering/index.py`, junto a `_index.md` y `README.md`: son el contrato de salida (CLAUDE.md §5), no una decisión del sistema de archivos.
