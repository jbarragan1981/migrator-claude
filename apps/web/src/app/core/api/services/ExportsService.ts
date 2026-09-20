/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import type { Observable } from 'rxjs';
import type { ExportCreateResponse } from '../models/ExportCreateResponse';
import type { Inventory } from '../models/Inventory';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
@Injectable({
    providedIn: 'root',
})
export class ExportsService {
    constructor(public readonly http: HttpClient) {}
    /**
     * Create Export
     * Multipart -> subida; cualquier otro content-type -> se interpreta como `{"path"}`.
     *
     * Los dos modos comparten la misma ruta HTTP (spec 06) pero necesitan cuerpos de
     * forma distinta, asi que el request se lee "a mano" en vez de declarar dos
     * parametros (`UploadFile` y un modelo pydantic) que FastAPI no puede combinar en
     * un unico endpoint.
     * @param formData
     * @returns ExportCreateResponse Successful Response
     * @throws ApiError
     */
    public createExportApiV1ExportsPost(
        formData: {
            /**
             * Uno o mas zips y/o el member-manifest-*.json.
             */
            file: Array<Blob>;
        },
    ): Observable<ExportCreateResponse> {
        return __request(OpenAPI, this.http, {
            method: 'POST',
            url: '/api/v1/exports',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                400: `Bad Request`,
                403: `Forbidden`,
                413: `Request Entity Too Large`,
            },
        });
    }
    /**
     * Get Export Inventory
     * @param exportId
     * @returns Inventory Successful Response
     * @throws ApiError
     */
    public getExportInventoryApiV1ExportsExportIdInventoryGet(
        exportId: string,
    ): Observable<Inventory> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/api/v1/exports/{export_id}/inventory',
            path: {
                'export_id': exportId,
            },
            errors: {
                404: `Not Found`,
                422: `Unprocessable Entity`,
            },
        });
    }
    /**
     * Delete Export
     * Ver decisiones en `services/lifecycle.py::delete_export` (id inexistente -> 404,
     * modo local solo borra `_output/`, modo subida borra el directorio de trabajo entero).
     * @param exportId
     * @returns void
     * @throws ApiError
     */
    public deleteExportApiV1ExportsExportIdDelete(
        exportId: string,
    ): Observable<void> {
        return __request(OpenAPI, this.http, {
            method: 'DELETE',
            url: '/api/v1/exports/{export_id}',
            path: {
                'export_id': exportId,
            },
            errors: {
                404: `Not Found`,
                409: `Conflict`,
                422: `Validation Error`,
            },
        });
    }
}
