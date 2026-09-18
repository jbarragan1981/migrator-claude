# 07 — Web (Angular)

## Objetivo
Interfaz local que guía a una persona no técnica: subir export → ver qué contiene → convertir → navegar y descargar.

## Pantallas
1. **Inicio / Carga** — dropzone para zips o manifiesto+zips; explicación de privacidad ("nada sale de tu equipo"); botón "Continuar".
2. **Inventario** — tabla por categoría (archivos, tamaño, ítems estimados, estado ✔/⚠); avisos de categorías o partes faltantes; selector de categorías a convertir.
3. **Conversión** — barra de progreso por categoría vía SSE; log de advertencias; botón cancelar.
4. **Resultado** — árbol de carpetas (izquierda) + visor Markdown (derecha, `ngx-markdown` o similar); búsqueda por título; botón "Descargar zip".
5. **Ajustes** — idioma (es/en), tema claro/oscuro, plantillas personalizadas (subir carpeta).

## Criterios de aceptación
- **CA-1** Todo el flujo con un fixture se completa en ≤ 5 clics desde Inicio hasta descarga.
- **CA-2** Sin conexión al API, la UI muestra estado de error traducible y botón de reintento (no pantalla en blanco).
- **CA-3** Cambiar idioma traduce el 100 % de los textos visibles (test que compara claves de `es.json` y `en.json`).
- **CA-4** Lighthouse accesibilidad ≥ 90 en Inicio y Resultado.
- **CA-5** A 360 px de ancho, todas las pantallas son usables sin scroll horizontal.
- **CA-6** `pnpm build` produce bundle inicial < 600 kB (lazy loading por feature).
- **CA-7** El front nunca lee el contenido de los zips: solo los envía a `POST /exports`.
