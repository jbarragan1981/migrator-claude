/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Body opcional de `POST /exports/{id}/convert`.
 *
 * `only` esta documentado en el spec 06 pero `usecases.convert.convert()` de core
 * todavia no acepta filtrar categorias (mismo pendiente que `--only` del CLI, ver
 * docs/specs/05-cli.md y STATUS.md): se acepta el campo para no romper el contrato,
 * pero no tiene efecto todavia (`services/jobs.py::start_conversion` deja un warning
 * en el log si se manda).
 */
export type ConvertRequest = {
    only?: (Array<string> | null);
    templates?: (string | null);
};

