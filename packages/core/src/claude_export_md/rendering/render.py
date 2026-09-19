"""Render de entidades a Markdown con Jinja2 (spec 04).

Módulo puro: construye texto, no escribe nada (eso es `adapters/sink_filesystem.py`) y
no mira el reloj (spec 04 CA-10). Las plantillas por defecto viven en `templates/` y el
usuario puede sustituirlas una a una con `--templates ./mis-plantillas` (CA-9).

Rinde tres entidades: `Memory` (M1), `Account` (M2, `light_metadata`) y `Project` con sus
`ProjectDoc` (M2). Las demás tienen su propio módulo cuando el render es grande
(`rendering/conversations.py`); estas caben aquí porque son frontmatter más un cuerpo
corto.

Decisiones propias de `Memory`, que el export no trae resueltas:

* **Título** — una memoria no tiene `title` en el export. Se usa el último segmento de
  `Memory.path` sin la extensión (`/people/Ana María.md` → `Ana María`), que es el único
  texto legible que trae el origen y además es estable. Las dos memorias de ruta
  sintética (ADR-0005) no tienen ningún texto que usar, así que llevan un título fijo
  que dice qué son (`Memoria de conversaciones`, `Memoria del proyecto <uuid>`).
* **Nombre del archivo** — la ruta de salida conserva la jerarquía de `Memory.path` con
  cada segmento slugificado (`/people/Ana María.md` → `memories/people/ana-maria.md`),
  porque `Memory.path` viene del export y no tiene por qué ser un nombre de archivo
  válido. Si dos rutas distintas slugifican igual, AMBAS reciben el hash corto de su
  ruta original: así el desempate no depende del orden en que se rendericen.

Decisiones propias de `Account`:

* **Ruta de salida** — `account/account.md` es una ruta FIJA (CLAUDE.md §5): no depende
  de ningún texto del export, al contrario que las memorias y las conversaciones.
* **Varias cuentas** — el export observado trae una sola, pero el parser no asume
  longitud 1 (spec 03, `light_metadata` CA-3). Si llegan varias, NINGUNA se queda
  `account/account.md`: todas pasan a `account/account-<hash>.md` y queda una
  advertencia en el `Report`. Así el nombre fijo nunca significa en silencio "la primera
  de varias", y —igual que en las memorias— el nombre de cada archivo depende solo de su
  propio `id`, no del orden de la colección.
* **Título** — una cuenta no tiene `title`: se usa `full_name`, y si no lo hay el correo,
  y si tampoco, el `uuid`. Nunca un título inventado.

Decisiones propias de `Project` y `ProjectDoc`:

* **Carpeta por proyecto** — `projects/<slug del nombre>/project.md` y sus documentos en
  `projects/<slug>/docs/<slug del filename>.md` (CLAUDE.md §5). Cada documento es una
  entidad propia (`type: project_doc`), no una sección del `project.md`, porque el día que
  se sepa dónde vive su contenido ese archivo ya existe y solo hay que llenarlo.
* **Colisiones** — si dos proyectos slugifican igual (`Q3: Ventas` y `Q3 / Ventas`), AMBOS
  reciben el hash corto de su `id`, igual que las memorias: así la carpeta de cada uno
  depende solo de sí mismo y no del orden de la colección. Lo mismo entre los documentos
  de un mismo proyecto.
* **Documento sin contenido** — `ProjectDoc.content is None` significa *el export no lo
  trae* (spec 03, projects CA-3 y ADR-0005). El `.md` del documento lo DICE
  (`DOC_CONTENT_UNAVAILABLE`) y la tabla del proyecto lo marca en su columna; nunca se
  deja un archivo vacío ni se inventa texto. Si algún export futuro sí trae el contenido,
  se inserta tal cual, como cualquier Markdown del usuario.
* **Título** — el `name` del proyecto y, en un documento, su `filename` COMPLETO (con
  extensión: no siempre es `.md`, y es el nombre que el usuario ve en Claude.ai). La
  extensión solo se quita para calcular el nombre del archivo de salida.
* **Instrucciones y descripción vacías** — `""` es un valor del export (spec 03,
  projects CA-2), así que la sección se imprime diciendo que está vacía; solo cuando el
  campo es `None` (no vino la clave) se omite la sección entera.
* **Conversaciones del proyecto** — el archivo del proyecto no las lista: el enlace va al
  revés, desde `conversations[].project_uuid` (CA-4). Quien lo cruza es
  `usecases/links.py`, y le pasa a `project_context` los `ConversationLink` resueltos:
  entonces la plantilla enumera cada conversación con su título y un enlace relativo al
  `.md` que escribió el sink. Si solo hay `Project.conversation_ids` (sin enlaces) se
  enumeran los uuids, y si no hay nada se dice explícitamente que ninguna conversación
  apunta al proyecto.

Decisiones propias de `Frame` (los artefactos de `frames`):

* **Ruta de salida** — `frames/<slug>.md`, plano: CLAUDE.md §5 dejaba la categoría "por
  investigar" y la Fase 0 ya la resolvió (`docs/export-format/frames.md`). No hay carpeta
  por artefacto como en los proyectos porque un artefacto es UN archivo: no tiene hijos
  que colgar. El slug sale del título de la versión activa (que es el nombre que el
  usuario vio en Claude.ai); si no hay títulos, del `kind`. Colisiones: AMBOS llevan el
  hash corto de su `id`, igual que memorias y proyectos.
* **Título** — el artefacto no tiene título propio, lo tienen sus versiones: se usa el de
  la versión activa; si `active_version` no coincide con ninguna (spec 03, frames CA-3),
  el de la primera versión que traiga uno; si ninguna, el `kind` (que es lo que el export
  dice que es el artefacto) y, en último caso, `UNTITLED_FRAME`. Nunca un título inventado.
* **Fecha de creación** — tampoco hay `created_at` a nivel de artefacto: se DERIVA de la
  versión más antigua de `versions[]` (el campo es obligatorio en el frontmatter, spec
  04). Es un dato que el export trae, no el reloj de la corrida (CA-10); si ninguna
  versión tiene fecha, el campo va en `null`.
* **Contenido no disponible** — ningún campo observado trae el código, el documento o la
  imagen del artefacto, y todavía no se sabe dónde viven (spec 03, frames CA-2). El `.md`
  lo DICE con todas las letras (`FRAME_CONTENT_UNAVAILABLE`, el mismo criterio que
  `DOC_CONTENT_UNAVAILABLE` en los documentos de proyecto) y además publica el JSON
  original íntegro (`Frame.payload`) en un `<details>`, para que no se pierda nada
  mientras se averigua. Nunca un bloque vacío en silencio (CLAUDE.md §1.3).
* **Versión activa incoherente** — si `active_version` no corresponde a ninguna versión,
  el archivo lo cuenta (`ACTIVE_VERSION_UNMATCHED_NOTE`) en vez de callarse la
  incoherencia; el parser ya dejó su advertencia en el `Report`.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined

from claude_export_md.domain.entities import (
    CONVERSATIONS_MEMORY_PATH,
    ORIGIN_CONVERSATIONS_MEMORY,
    ORIGIN_MEMORY_FILES,
    Account,
    Frame,
    FrameVersion,
    Memory,
    Project,
    ProjectDoc,
)
from claude_export_md.rendering.filters import (
    code_fence,
    hhmm,
    iso_utc,
    jsonable,
    md_cell,
    short_hash,
    slugify,
    yaml_block,
    yaml_inline,
    yaml_value,
)
from claude_export_md.rendering.links import ConversationLink, day, relative_link

logger = logging.getLogger(__name__)

#: Carpeta de las plantillas que trae la librería.
TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Filtros que ve CUALQUIER plantilla, incluidas las del usuario (`--templates`).
#: Esta tabla y la de `docs/specs/04-markdown-output.md` §Plantillas son el mismo
#: contrato: con `StrictUndefined`, un filtro documentado y no registrado aquí hace
#: reventar la plantilla del usuario con `TemplateAssertionError`.
FILTERS = {
    "code_fence": code_fence,
    "hhmm": hhmm,
    "iso_utc": iso_utc,
    "md_cell": md_cell,
    "slugify": slugify,
    "yaml_block": yaml_block,
    "yaml_inline": yaml_inline,
    "yaml_value": yaml_value,
}

#: Plantilla y `type` de frontmatter de una memoria.
MEMORY_TEMPLATE = "memory.md.j2"
TYPE_MEMORY = "memory"

#: Plantilla y `type` de frontmatter del perfil de la cuenta.
ACCOUNT_TEMPLATE = "account.md.j2"
TYPE_ACCOUNT = "account"

#: Plantillas y `type` de frontmatter de un proyecto y de sus documentos.
PROJECT_TEMPLATE = "project.md.j2"
PROJECT_DOC_TEMPLATE = "project_doc.md.j2"
TYPE_PROJECT = "project"
TYPE_PROJECT_DOC = "project_doc"

#: Plantilla y `type` de frontmatter de un artefacto de `frames`.
FRAME_TEMPLATE = "frame.md.j2"
TYPE_FRAME = "frame"

#: Carpeta de las memorias dentro de la salida (CLAUDE.md §5).
MEMORIES_DIR = "memories"
#: Carpeta y archivo fijos del perfil de la cuenta (CLAUDE.md §5).
ACCOUNT_DIR = "account"
ACCOUNT_STEM = "account"
#: Carpeta de los proyectos y nombres de sus archivos dentro de ella (CLAUDE.md §5).
PROJECTS_DIR = "projects"
PROJECT_STEM = "project"
PROJECT_DOCS_DIR = "docs"
#: Carpeta de los artefactos dentro de la salida (CLAUDE.md §5).
FRAMES_DIR = "frames"
#: Extensión de todo lo que genera la herramienta.
MARKDOWN_SUFFIX = ".md"
#: Extensiones que se quitan del último segmento antes de slugificarlo.
TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})

#: Títulos de las memorias que no tienen ningún texto propio (ADR-0005).
CONVERSATIONS_MEMORY_TITLE = "Memoria de conversaciones"
PROJECT_MEMORY_TITLE = "Memoria del proyecto"

#: Etiqueta común a todas las memorias, más la del origen y la carpeta de la ruta.
TAG_MEMORY = "memory"
TAG_PROJECT = "project"
#: Etiqueta del perfil de la cuenta.
TAG_ACCOUNT = "account"
#: Etiqueta de un documento de proyecto (además de la del proyecto).
TAG_PROJECT_DOC = "project-doc"
#: Etiqueta de un artefacto (se le suma el `kind` cuando el export lo trae).
TAG_FRAME = "frame"

#: Título de un proyecto al que el usuario nunca le puso nombre.
UNTITLED_PROJECT = "Proyecto sin título"
#: Título de un artefacto del que ninguna versión trae uno y que tampoco trae `kind`.
UNTITLED_FRAME = "Artefacto sin título"

#: Lo que dice el `.md` de un documento cuyo contenido no viaja en el export (CA-3).
DOC_CONTENT_UNAVAILABLE = (
    "El export no incluye el contenido de este documento: `docs[]` solo trae su nombre, "
    "su identificador y su fecha. No se ha inventado ningún texto."
)
#: Columna "Contenido" de la tabla de documentos del proyecto.
DOC_STATUS_UNAVAILABLE = "No disponible en este export"
DOC_STATUS_AVAILABLE = "Incluido en el archivo"

#: Lo que dice el `.md` de un artefacto cuyo contenido no viaja en el export (frames CA-2).
#: Mismo criterio y misma forma que `DOC_CONTENT_UNAVAILABLE`: qué falta, y que no se ha
#: inventado nada. Debajo, el `.md` publica igualmente el JSON original completo.
FRAME_CONTENT_UNAVAILABLE = (
    "El export no incluye el contenido de este artefacto (ni el código, ni el documento, "
    "ni la imagen): `frames-000/artifacts/` solo trae su metadata —versiones, títulos, "
    "descripciones y fechas—. No se ha inventado ningún texto."
)
#: Solo se dice cuando de verdad hay JSON que enseñar (si no, el aviso mentiría).
FRAME_PAYLOAD_AVAILABLE = (
    "Lo que sí está: el JSON original del artefacto, íntegro y sin tocar, al final de este archivo."
)

#: Frases para las secciones que no tienen nada que mostrar (nunca vacías en silencio).
EMPTY_DESCRIPTION_NOTE = "El export trae la descripción de este proyecto vacía."
EMPTY_INSTRUCTIONS_NOTE = "El export trae las instrucciones de este proyecto vacías."
NO_DOCS_NOTE = "Este proyecto no tiene documentos en el export."
NO_CONVERSATIONS_NOTE = "Ninguna conversación de este export apunta a este proyecto."
NO_VERSIONS_NOTE = "El export no trae ninguna versión de este artefacto."
NO_ACTIVE_VERSION_NOTE = "El export no dice cuál es la versión activa de este artefacto."
#: Spec 03, frames CA-3: se tolera, pero el archivo lo cuenta en vez de callarlo.
ACTIVE_VERSION_UNMATCHED_NOTE = (
    "El export declara `{active}` como versión activa, pero no coincide con el "
    "identificador de ninguna de las versiones de este artefacto."
)

#: Ruta fija del perfil de la cuenta cuando el export trae una sola (CLAUDE.md §5).
ACCOUNT_PATH = f"{ACCOUNT_DIR}/{ACCOUNT_STEM}{MARKDOWN_SUFFIX}"

#: Advertencia de un export con más de una cuenta (ver las decisiones del módulo).
MULTIPLE_ACCOUNTS_WARNING = (
    "El export trae {count} cuentas y {path} es una ruta única: cada cuenta se guarda "
    "como {folder}/{stem}-<hash>{suffix} para que ninguna pise a otra"
)

#: Campo de `extra` que pone el parser y que en el frontmatter va al primer nivel.
SOURCE_FILE_KEY = "source_file"
ORIGIN_KEY = "origin"


# ------------------------------------------------------------------- entorno


def build_environment(user_templates: Path | str | None = None) -> Environment:
    """Entorno de Jinja2 con los filtros propios y, si se pasa, las plantillas del usuario.

    `autoescape` queda apagado a propósito: la salida es Markdown, no HTML, y escapar
    sería corromper el texto del usuario (skill `markdown-template`, regla 5).
    `StrictUndefined` hace que una plantilla propia que use una variable inexistente
    falle en vez de escribir un hueco silencioso.
    """
    loaders: list[FileSystemLoader] = []
    if user_templates is not None:
        loaders.append(FileSystemLoader(str(user_templates)))
    loaders.append(FileSystemLoader(str(TEMPLATES_DIR)))
    environment = Environment(
        loader=ChoiceLoader(loaders),
        autoescape=False,  # noqa: S701 - Markdown, no HTML
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    environment.filters.update(FILTERS)
    return environment


# ------------------------------------------------------------------ memorias


def _origin(memory: Memory) -> str | None:
    value = (memory.model_extra or {}).get(ORIGIN_KEY)
    return value if isinstance(value, str) else None


def _last_segment(path: str) -> str:
    """Último tramo de la ruta sin la extensión de texto: `/people/Ana.md` → `Ana`."""
    name = PurePosixPath(path).name
    if PurePosixPath(name).suffix.lower() in TEXT_SUFFIXES:
        return PurePosixPath(name).stem
    return name


def memory_title(memory: Memory) -> str:
    """Título legible de una memoria; ver la nota de decisiones del módulo."""
    if _origin(memory) == ORIGIN_CONVERSATIONS_MEMORY or memory.path == CONVERSATIONS_MEMORY_PATH:
        return CONVERSATIONS_MEMORY_TITLE
    if memory.project_id:
        return f"{PROJECT_MEMORY_TITLE} {memory.project_id}"
    return _last_segment(memory.path) or memory.path


def memory_tags(memory: Memory) -> list[str]:
    """Etiquetas del frontmatter: siempre `memory`, más el origen y la carpeta."""
    tags = [TAG_MEMORY]
    origin = _origin(memory)
    if origin:
        tags.append(slugify(origin))
    if memory.project_id:
        tags.append(TAG_PROJECT)
    if origin in (None, ORIGIN_MEMORY_FILES):
        # Solo las rutas reales tienen carpetas con significado para el usuario;
        # las sintéticas (`_project_memories`) son nuestras, no del export.
        tags.extend(slugify(part) for part in PurePosixPath(memory.path).parts[:-1] if part != "/")
    return list(dict.fromkeys(tag for tag in tags if tag))


def memory_output_path(memory: Memory) -> str:
    """Ruta del `.md` relativa a la raíz de la salida, sin resolver colisiones."""
    parts = [part for part in memory.path.split("/") if part]
    folders = [slugify(part) for part in parts[:-1]]
    name = slugify(_last_segment(memory.path)) if parts else slugify("")
    return "/".join([MEMORIES_DIR, *folders, name + MARKDOWN_SUFFIX])


def assign_output_paths(memories: Sequence[Memory]) -> list[tuple[Memory, str]]:
    """Ruta de salida definitiva de cada memoria, con las colisiones ya desempatadas.

    Dos `Memory.path` distintos pueden slugificar igual (`/people/Ana María.md` y
    `/people/ana-maria!.md`). En ese caso las dos llevan el hash corto de su ruta
    original, de forma que el nombre de cada archivo depende solo de su propia ruta y no
    del orden de la colección (spec 04 CA-1).
    """
    assigned = [(memory, memory_output_path(memory)) for memory in memories]
    repeated = {path for path, times in Counter(path for _, path in assigned).items() if times > 1}
    return [
        (memory, _disambiguate(memory, path) if path in repeated else path)
        for memory, path in assigned
    ]


def _disambiguate(memory: Memory, path: str) -> str:
    return f"{path.removesuffix(MARKDOWN_SUFFIX)}-{short_hash(memory.path)}{MARKDOWN_SUFFIX}"


def memory_context(memory: Memory) -> dict[str, Any]:
    """Variables que ve `memory.md.j2` (documentadas en la propia plantilla)."""
    extra = dict(memory.model_extra or {})
    source_file = extra.pop(SOURCE_FILE_KEY, None)
    return {
        "memory": memory,
        "id": memory.path,
        "type": TYPE_MEMORY,
        "title": memory_title(memory),
        # El export no trae fecha de creación de una memoria; el campo es obligatorio
        # en el frontmatter (spec 04) y se emite en null antes que inventarlo.
        "created_at": None,
        "updated_at": iso_utc(memory.updated_at),
        "source_file": source_file,
        "project_id": memory.project_id,
        "tags": memory_tags(memory),
        "extra": jsonable(extra),
        "content": memory.content,
    }


def render_memory(memory: Memory, environment: Environment | None = None) -> str:
    """Markdown completo de una memoria: frontmatter + su contenido tal cual."""
    env = environment if environment is not None else build_environment()
    rendered = env.get_template(MEMORY_TEMPLATE).render(**memory_context(memory))
    return rendered.rstrip("\n") + "\n"


def render_memories(
    memories: Iterable[Memory], environment: Environment | None = None
) -> list[tuple[str, str]]:
    """`(ruta relativa, markdown)` de cada memoria, lista para escribir."""
    env = environment if environment is not None else build_environment()
    return [
        (path, render_memory(memory, env)) for memory, path in assign_output_paths(list(memories))
    ]


# -------------------------------------------------------------------- cuenta


def account_title(account: Account) -> str:
    """Lo más legible que traiga el export: nombre, correo o `uuid` (nunca inventado)."""
    return (account.display_name or "").strip() or (account.email or "").strip() or account.id


def account_tags(account: Account) -> list[str]:  # noqa: ARG001 - firma común de los tags
    """Etiquetas del frontmatter. Una cuenta no tiene de dónde sacar más."""
    return [TAG_ACCOUNT]


def account_output_path(account: Account, shared: bool = False) -> str:
    """`account/account.md`; con `shared`, el nombre propio de esta cuenta.

    `shared=True` significa *el export trae más de una cuenta*: entonces ninguna puede
    quedarse la ruta fija de CLAUDE.md §5, y cada una lleva el hash corto de su `id`
    (estable y libre del orden de la colección).
    """
    if not shared:
        return ACCOUNT_PATH
    return f"{ACCOUNT_DIR}/{ACCOUNT_STEM}-{short_hash(account.id)}{MARKDOWN_SUFFIX}"


def assign_account_paths(accounts: Sequence[Account]) -> list[tuple[Account, str]]:
    """Ruta de salida definitiva de cada cuenta (una sola → la ruta fija)."""
    shared = len(accounts) > 1
    return [(account, account_output_path(account, shared)) for account in accounts]


def account_path_warnings(accounts: Sequence[Account]) -> list[str]:
    """Lo que hay que contarle al usuario si el export trajo más de una cuenta."""
    if len(accounts) <= 1:
        return []
    return [
        MULTIPLE_ACCOUNTS_WARNING.format(
            count=len(accounts),
            path=ACCOUNT_PATH,
            folder=ACCOUNT_DIR,
            stem=ACCOUNT_STEM,
            suffix=MARKDOWN_SUFFIX,
        )
    ]


def account_context(account: Account) -> dict[str, Any]:
    """Variables que ve `account.md.j2` (documentadas en la propia plantilla)."""
    extra = dict(account.model_extra or {})
    source_file = extra.pop(SOURCE_FILE_KEY, None)
    return {
        "account": account,
        "id": account.id,
        "type": TYPE_ACCOUNT,
        "title": account_title(account),
        # `light_metadata` no trae ninguna fecha de la cuenta; los dos campos son
        # obligatorios en el frontmatter (spec 04) y se emiten en null antes que
        # inventarlos con el reloj de la corrida (CA-10).
        "created_at": None,
        "updated_at": None,
        "source_file": source_file,
        "tags": account_tags(account),
        "extra": jsonable(extra),
        "email": account.email,
        "display_name": account.display_name,
        "settings": sorted(jsonable(account.settings).items()),
    }


def render_account(account: Account, environment: Environment | None = None) -> str:
    """Markdown del perfil de la cuenta: frontmatter + una tabla con sus datos."""
    env = environment if environment is not None else build_environment()
    rendered = env.get_template(ACCOUNT_TEMPLATE).render(**account_context(account))
    return rendered.rstrip("\n") + "\n"


def render_accounts(
    accounts: Iterable[Account], environment: Environment | None = None
) -> list[tuple[str, str]]:
    """`(ruta relativa, markdown)` de cada cuenta, lista para escribir."""
    env = environment if environment is not None else build_environment()
    return [
        (path, render_account(account, env))
        for account, path in assign_account_paths(list(accounts))
    ]


# ----------------------------------------------------------------- proyectos


def project_title(project: Project) -> str:
    """`name` del export; si vino vacío se dice que no tiene nombre, no se inventa uno."""
    return (project.name or "").strip() or UNTITLED_PROJECT


def project_tags(project: Project) -> list[str]:  # noqa: ARG001 - firma común de los tags
    """Etiquetas del frontmatter de un proyecto."""
    return [TAG_PROJECT]


def project_doc_tags(doc: ProjectDoc) -> list[str]:  # noqa: ARG001 - firma común
    """Etiquetas del frontmatter de un documento de proyecto."""
    return [TAG_PROJECT_DOC, TAG_PROJECT]


def project_dir(project: Project, shared: bool = False) -> str:
    """Carpeta del proyecto: `projects/<slug>` (CLAUDE.md §5).

    `shared=True` significa *otro proyecto slugifica igual*: entonces los dos llevan el
    hash corto de su `id`, de forma que la carpeta de cada uno depende solo de sí mismo.
    """
    slug = slugify(project.name or "")
    if shared:
        slug = f"{slug}-{short_hash(project.id)}"
    return f"{PROJECTS_DIR}/{slug}"


def assign_project_dirs(projects: Sequence[Project]) -> list[tuple[Project, str]]:
    """Carpeta definitiva de cada proyecto, con las colisiones de slug ya desempatadas."""
    assigned = [(project, project_dir(project)) for project in projects]
    repeated = {
        directory for directory, times in Counter(d for _p, d in assigned).items() if times > 1
    }
    return [
        (project, project_dir(project, shared=True) if directory in repeated else directory)
        for project, directory in assigned
    ]


def project_output_path(project: Project, directory: str | None = None) -> str:
    """Ruta del `project.md` relativa a la raíz de la salida."""
    base = directory if directory is not None else project_dir(project)
    return f"{base}/{PROJECT_STEM}{MARKDOWN_SUFFIX}"


def project_doc_title(doc: ProjectDoc) -> str:
    """`filename` tal cual (la extensión es parte del nombre), o el id si no vino."""
    return (doc.filename or "").strip() or doc.id


def project_doc_paths(
    project: Project, directory: str | None = None
) -> list[tuple[ProjectDoc, str]]:
    """Ruta de cada documento: `projects/<slug>/docs/<slug del filename>.md`.

    Dos `filename` distintos pueden slugificar igual (`Guía.md` y `guia!.md`): en ese caso
    los dos llevan el hash corto de su `id`, como en las memorias.
    """
    base = directory if directory is not None else project_dir(project)
    names = [_doc_stem(doc) for doc in project.docs]
    repeated = {name for name, times in Counter(names).items() if times > 1}
    paths = []
    for doc, name in zip(project.docs, names, strict=True):
        stem = f"{name}-{short_hash(doc.id)}" if name in repeated else name
        paths.append((doc, f"{base}/{PROJECT_DOCS_DIR}/{stem}{MARKDOWN_SUFFIX}"))
    return paths


def _doc_stem(doc: ProjectDoc) -> str:
    """Nombre del archivo de un documento, sin extensión y ya slugificado."""
    return slugify(_last_segment(doc.filename) if doc.filename else doc.id)


def _source_file(project: Project) -> str | None:
    """Archivo del export del que salió el proyecto (lo anota el parser en `extra`)."""
    value = (project.model_extra or {}).get(SOURCE_FILE_KEY)
    return value if isinstance(value, str) else None


def project_conversation_rows(
    conversations: Iterable[ConversationLink], path: str
) -> list[dict[str, Any]]:
    """Filas de la sección `## Conversaciones`, con el enlace desde `path` (el project.md).

    Las conversaciones llegan ya ordenadas por quien las cruzó (`usecases/links.py`);
    aquí solo se convierte su ruta absoluta desde la raíz en el enlace relativo que hay
    que escribir dentro de este archivo.
    """
    return [
        {
            "id": link.id,
            "title": link.title,
            "link": relative_link(path, link.path),
            "day": day(link.date),
        }
        for link in conversations
    ]


def project_context(
    project: Project,
    directory: str | None = None,
    conversations: Iterable[ConversationLink] = (),
) -> dict[str, Any]:
    """Variables que ve `project.md.j2` (documentadas en la propia plantilla)."""
    extra = dict(project.model_extra or {})
    source_file = extra.pop(SOURCE_FILE_KEY, None)
    base = directory if directory is not None else project_dir(project)
    docs = [
        {
            "doc": doc,
            "title": project_doc_title(doc),
            "filename": doc.filename,
            "created_at": iso_utc(doc.created_at),
            "link": path.removeprefix(f"{base}/"),
            "available": doc.content is not None,
            "status": DOC_STATUS_AVAILABLE if doc.content is not None else DOC_STATUS_UNAVAILABLE,
        }
        for doc, path in project_doc_paths(project, base)
    ]
    return {
        "project": project,
        "id": project.id,
        "type": TYPE_PROJECT,
        "title": project_title(project),
        "created_at": iso_utc(project.created_at),
        "updated_at": iso_utc(project.updated_at),
        "source_file": source_file,
        "creator_id": project.creator_id,
        "tags": project_tags(project),
        "extra": jsonable(extra),
        # CA-2: `""` se emite (la sección dice que está vacía); solo `None` se omite.
        "description": project.description,
        "instructions": project.instructions,
        "docs": docs,
        "doc_count": len(project.docs),
        "conversations": list(project.conversation_ids),
        "conversation_rows": project_conversation_rows(
            conversations, project_output_path(project, base)
        ),
        "notes": {
            "empty_description": EMPTY_DESCRIPTION_NOTE,
            "empty_instructions": EMPTY_INSTRUCTIONS_NOTE,
            "no_docs": NO_DOCS_NOTE,
            "no_conversations": NO_CONVERSATIONS_NOTE,
        },
    }


def project_doc_context(project: Project, doc: ProjectDoc) -> dict[str, Any]:
    """Variables que ve `project_doc.md.j2` (documentadas en la propia plantilla)."""
    return {
        "doc": doc,
        "project": project,
        "id": doc.id,
        "type": TYPE_PROJECT_DOC,
        "title": project_doc_title(doc),
        "created_at": iso_utc(doc.created_at),
        # El export no trae fecha de actualización de un documento; el campo es
        # obligatorio en el frontmatter (spec 04) y se emite en null antes que inventarlo.
        "updated_at": None,
        # El documento salió del mismo archivo que su proyecto.
        "source_file": _source_file(project),
        "project_id": project.id,
        "project_title": project_title(project),
        "project_link": f"../{PROJECT_STEM}{MARKDOWN_SUFFIX}",
        "filename": doc.filename,
        "tags": project_doc_tags(doc),
        "extra": jsonable(dict(doc.model_extra or {})),
        "content": doc.content,
        "notice": None if doc.content is not None else DOC_CONTENT_UNAVAILABLE,
    }


def render_project(
    project: Project,
    environment: Environment | None = None,
    directory: str | None = None,
    conversations: Iterable[ConversationLink] = (),
) -> list[tuple[str, str]]:
    """`(ruta relativa, markdown)` del `project.md` y de cada uno de sus documentos.

    `directory` permite imponer la carpeta que ya asignó `assign_project_dirs` (para que
    el `project.md`, sus documentos y los enlaces entre ellos digan lo mismo); si no se
    pasa, se calcula la carpeta natural del proyecto. `conversations` son los enlaces que
    resolvió `usecases/links.py` (spec 03, projects CA-4); sin ellos el archivo enumera
    los `conversation_ids` que traiga la entidad.
    """
    env = environment if environment is not None else build_environment()
    base = directory if directory is not None else project_dir(project)
    rendered = [
        (
            project_output_path(project, base),
            _render(env, PROJECT_TEMPLATE, project_context(project, base, conversations)),
        )
    ]
    rendered.extend(
        (path, _render(env, PROJECT_DOC_TEMPLATE, project_doc_context(project, doc)))
        for doc, path in project_doc_paths(project, base)
    )
    return rendered


def render_projects(
    projects: Iterable[Project], environment: Environment | None = None
) -> list[tuple[str, str]]:
    """`(ruta relativa, markdown)` de todos los archivos de todos los proyectos."""
    env = environment if environment is not None else build_environment()
    return [
        file
        for project, directory in assign_project_dirs(list(projects))
        for file in render_project(project, env, directory)
    ]


# ------------------------------------------------------------------- frames


def _version_titles(frame: Frame) -> Iterable[str]:
    """Títulos legibles de las versiones, la activa primero (ver las decisiones)."""
    active = frame.active()
    versions = [active, *frame.versions] if active is not None else list(frame.versions)
    return ((version.title or "").strip() for version in versions)


def frame_title(frame: Frame) -> str:
    """Título de la versión activa, si no de cualquier versión, si no el `kind`."""
    for title in _version_titles(frame):
        if title:
            return title
    return (frame.kind or "").strip() or UNTITLED_FRAME


def frame_created_at(frame: Frame) -> datetime | None:
    """Fecha de la versión MÁS ANTIGUA: el artefacto no trae `created_at` propio.

    Es un dato del export, no el reloj de la corrida (spec 04 CA-10). Si ninguna versión
    trae fecha se devuelve `None` y el frontmatter la emite en `null`.
    """
    dates = [version.created_at for version in frame.versions if version.created_at is not None]
    return min(dates) if dates else None


def frame_tags(frame: Frame) -> list[str]:
    """Etiquetas del frontmatter: `frame` y, si el export lo trae, su `kind`."""
    tags = [TAG_FRAME]
    if frame.kind and frame.kind.strip():
        tags.append(slugify(frame.kind))
    return list(dict.fromkeys(tags))


def frame_output_path(frame: Frame, shared: bool = False) -> str:
    """Ruta del `.md` del artefacto: `frames/<slug>.md` (ver las decisiones del módulo).

    `shared=True` significa *otro artefacto slugifica igual*: entonces los dos llevan el
    hash corto de su `id`, de forma que el nombre de cada uno depende solo de sí mismo.
    """
    stem = slugify(frame_title(frame))
    if shared:
        stem = f"{stem}-{short_hash(frame.id)}"
    return f"{FRAMES_DIR}/{stem}{MARKDOWN_SUFFIX}"


def assign_frame_paths(frames: Sequence[Frame]) -> list[tuple[Frame, str]]:
    """Ruta de salida definitiva de cada artefacto, con las colisiones ya desempatadas."""
    assigned = [(frame, frame_output_path(frame)) for frame in frames]
    repeated = {path for path, times in Counter(path for _f, path in assigned).items() if times > 1}
    return [
        (frame, frame_output_path(frame, shared=True) if path in repeated else path)
        for frame, path in assigned
    ]


def _version_row(version: FrameVersion, active: FrameVersion | None) -> dict[str, Any]:
    """Una fila de la tabla de versiones (`versions` en la plantilla)."""
    return {
        "version": version,
        "id": version.id,
        "title": version.title,
        "description": version.description,
        "created_at": iso_utc(version.created_at),
        "active": active is not None and version.id == active.id,
    }


def frame_context(frame: Frame) -> dict[str, Any]:
    """Variables que ve `frame.md.j2` (documentadas en la propia plantilla)."""
    extra = dict(frame.model_extra or {})
    source_file = extra.pop(SOURCE_FILE_KEY, None)
    active = frame.active()
    unmatched = frame.active_version is not None and active is None
    return {
        "frame": frame,
        "id": frame.id,
        "type": TYPE_FRAME,
        "title": frame_title(frame),
        "created_at": iso_utc(frame_created_at(frame)),
        "updated_at": iso_utc(frame.updated_at),
        "source_file": source_file,
        "kind": frame.kind,
        "visibility": frame.visibility,
        "owner_account": frame.owner_account,
        "active_version": frame.active_version,
        "active": None if active is None else _version_row(active, active),
        "versions": [_version_row(version, active) for version in frame.versions],
        "version_count": len(frame.versions),
        "tags": frame_tags(frame),
        "extra": jsonable(extra),
        # CA-2: el JSON original entero a la vista, para no perder nada mientras no se
        # sepa dónde vive el contenido. Claves ordenadas para que el archivo no cambie
        # entre corridas (spec 04 CA-1).
        "payload_json": _payload_json(frame.payload),
        "notice": FRAME_CONTENT_UNAVAILABLE,
        "notes": {
            "no_versions": NO_VERSIONS_NOTE,
            "no_active_version": NO_ACTIVE_VERSION_NOTE,
            "payload_available": FRAME_PAYLOAD_AVAILABLE,
            "active_unmatched": (
                ACTIVE_VERSION_UNMATCHED_NOTE.format(active=frame.active_version)
                if unmatched
                else None
            ),
        },
    }


def _payload_json(payload: dict[str, Any]) -> str:
    """El JSON original formateado y con las claves ordenadas; `""` si no hay nada."""
    if not payload:
        return ""
    return json.dumps(jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True)


def render_frame(frame: Frame, environment: Environment | None = None) -> str:
    """Markdown de un artefacto: su metadata, sus versiones y el JSON original."""
    env = environment if environment is not None else build_environment()
    return _render(env, FRAME_TEMPLATE, frame_context(frame))


def render_frames(
    frames: Iterable[Frame], environment: Environment | None = None
) -> list[tuple[str, str]]:
    """`(ruta relativa, markdown)` de cada artefacto, lista para escribir."""
    env = environment if environment is not None else build_environment()
    return [(path, render_frame(frame, env)) for frame, path in assign_frame_paths(list(frames))]


def _render(environment: Environment, template: str, context: dict[str, Any]) -> str:
    """Render de una plantilla con el salto de línea final normalizado."""
    return environment.get_template(template).render(**context).rstrip("\n") + "\n"


__all__ = [
    "ACCOUNT_DIR",
    "ACCOUNT_PATH",
    "ACCOUNT_STEM",
    "ACCOUNT_TEMPLATE",
    "ACTIVE_VERSION_UNMATCHED_NOTE",
    "CONVERSATIONS_MEMORY_TITLE",
    "DOC_CONTENT_UNAVAILABLE",
    "DOC_STATUS_AVAILABLE",
    "DOC_STATUS_UNAVAILABLE",
    "EMPTY_DESCRIPTION_NOTE",
    "EMPTY_INSTRUCTIONS_NOTE",
    "FRAMES_DIR",
    "FRAME_CONTENT_UNAVAILABLE",
    "FRAME_PAYLOAD_AVAILABLE",
    "FRAME_TEMPLATE",
    "MEMORIES_DIR",
    "MEMORY_TEMPLATE",
    "MULTIPLE_ACCOUNTS_WARNING",
    "NO_ACTIVE_VERSION_NOTE",
    "NO_CONVERSATIONS_NOTE",
    "NO_DOCS_NOTE",
    "NO_VERSIONS_NOTE",
    "PROJECTS_DIR",
    "PROJECT_DOCS_DIR",
    "PROJECT_DOC_TEMPLATE",
    "PROJECT_MEMORY_TITLE",
    "PROJECT_STEM",
    "PROJECT_TEMPLATE",
    "TEMPLATES_DIR",
    "TYPE_ACCOUNT",
    "TYPE_FRAME",
    "TYPE_MEMORY",
    "TYPE_PROJECT",
    "TYPE_PROJECT_DOC",
    "UNTITLED_FRAME",
    "UNTITLED_PROJECT",
    "account_context",
    "account_output_path",
    "account_path_warnings",
    "account_tags",
    "account_title",
    "assign_account_paths",
    "assign_frame_paths",
    "assign_output_paths",
    "assign_project_dirs",
    "build_environment",
    "frame_context",
    "frame_created_at",
    "frame_output_path",
    "frame_tags",
    "frame_title",
    "memory_context",
    "memory_output_path",
    "memory_tags",
    "memory_title",
    "project_context",
    "project_conversation_rows",
    "project_dir",
    "project_doc_context",
    "project_doc_paths",
    "project_doc_tags",
    "project_doc_title",
    "project_output_path",
    "project_tags",
    "project_title",
    "render_account",
    "render_accounts",
    "render_frame",
    "render_frames",
    "render_memories",
    "render_memory",
    "render_project",
    "render_projects",
]
