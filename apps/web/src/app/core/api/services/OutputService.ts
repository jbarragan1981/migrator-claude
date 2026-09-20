/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import type { Observable } from 'rxjs';
import type { OutputTreeResponse } from '../models/OutputTreeResponse';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
@Injectable({
    providedIn: 'root',
})
export class OutputService {
    constructor(public readonly http: HttpClient) {}
    /**
     * Get Output Tree
     * @param exportId
     * @returns OutputTreeResponse Successful Response
     * @throws ApiError
     */
    public getOutputTreeApiV1ExportsExportIdOutputTreeGet(
        exportId: string,
    ): Observable<OutputTreeResponse> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/api/v1/exports/{export_id}/output/tree',
            path: {
                'export_id': exportId,
            },
            errors: {
                404: `Not Found`,
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Output File
     * @param exportId
     * @param path
     * @returns any Contenido crudo del archivo (content-type real: guess_media_type).
     * @throws ApiError
     */
    public getOutputFileApiV1ExportsExportIdOutputFileGet(
        exportId: string,
        path: string,
    ): Observable<any> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/api/v1/exports/{export_id}/output/file',
            path: {
                'export_id': exportId,
            },
            query: {
                'path': path,
            },
            errors: {
                400: `Bad Request`,
                404: `Not Found`,
                422: `Unprocessable Entity`,
            },
        });
    }
    /**
     * Download Export
     * @param exportId
     * @returns any El arbol convertido completo, en zip.
     * @throws ApiError
     */
    public downloadExportApiV1ExportsExportIdDownloadGet(
        exportId: string,
    ): Observable<any> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/api/v1/exports/{export_id}/download',
            path: {
                'export_id': exportId,
            },
            errors: {
                404: `Not Found`,
                422: `Validation Error`,
            },
        });
    }
}
