/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProgressEventSchema } from './ProgressEventSchema';
/**
 * `GET /jobs/{id}` (spec 06): `{status, progress, counts, errors}` mas el motivo
 * de un `failed` (incluido `"timeout"`, CA-6) y las advertencias, que no rompen el
 * contrato del spec (son un campo adicional, no uno de los pedidos).
 */
export type JobStatusResponse = {
    status: JobStatusResponse.status;
    progress: Array<ProgressEventSchema>;
    counts?: (Record<string, number> | null);
    errors?: (number | null);
    warnings?: (number | null);
    reason?: (string | null);
};
export namespace JobStatusResponse {
    export enum status {
        PENDING = 'pending',
        RUNNING = 'running',
        DONE = 'done',
        FAILED = 'failed',
    }
}

