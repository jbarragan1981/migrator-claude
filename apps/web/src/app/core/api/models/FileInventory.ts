/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Una entrada del inventario: tamaño, tipo raíz y muestra de la estructura.
 *
 * Es **un archivo nombrable** (`path`) o **un grupo de archivos** (`pattern` + `count`),
 * nunca las dos cosas. Solo se conserva el nombre literal cuando lo decide el formato
 * del export y no el contenido del usuario (`domain/redaction.py`, ADR-0004): los
 * nombres hoja variables —`memories-000/people/<persona>.md`— se colapsan en
 * `{"pattern": "memories-000/people*.md", "count": 37}`.
 */
export type FileInventory = Record<string, any>;
