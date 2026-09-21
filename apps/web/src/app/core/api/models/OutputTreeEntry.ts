/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Una fila del arbol de salida: ruta relativa POSIX bajo `_output/`.
 *
 * Se devuelve como LISTA PLANA (`OutputTreeResponse.entries`), no como arbol
 * anidado: cada entrada ya trae su ruta completa (`"conversations/2026/09"`,
 * `"conversations/2026/09/2026-09-01_titulo_ab12cd34.md"`...), asi que el cliente
 * puede reconstruir la jerarquia partiendo por `/` si la quiere mostrar como arbol,
 * sin que el servidor tenga que modelar un schema recursivo para eso.
 */
export type OutputTreeEntry = {
    path: string;
    kind: OutputTreeEntry.kind;
    size?: (number | null);
};
export namespace OutputTreeEntry {
    export enum kind {
        FILE = 'file',
        DIR = 'dir',
    }
}

