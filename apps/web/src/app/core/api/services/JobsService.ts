/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import type { Observable } from 'rxjs';
import type { ConvertRequest } from '../models/ConvertRequest';
import type { JobCreateResponse } from '../models/JobCreateResponse';
import type { JobStatusResponse } from '../models/JobStatusResponse';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
@Injectable({
    providedIn: 'root',
})
export class JobsService {
    constructor(public readonly http: HttpClient) {}
    /**
     * Convert Export
     * @param exportId
     * @param requestBody
     * @returns JobCreateResponse Successful Response
     * @throws ApiError
     */
    public convertExportApiV1ExportsExportIdConvertPost(
        exportId: string,
        requestBody?: (ConvertRequest | null),
    ): Observable<JobCreateResponse> {
        return __request(OpenAPI, this.http, {
            method: 'POST',
            url: '/api/v1/exports/{export_id}/convert',
            path: {
                'export_id': exportId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                404: `Not Found`,
                409: `Conflict`,
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Job
     * @param jobId
     * @returns JobStatusResponse Successful Response
     * @throws ApiError
     */
    public getJobApiV1JobsJobIdGet(
        jobId: string,
    ): Observable<JobStatusResponse> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/api/v1/jobs/{job_id}',
            path: {
                'job_id': jobId,
            },
            errors: {
                404: `Not Found`,
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Job Events
     * @param jobId
     * @returns any progress/done/error, uno por linea 'data: ...' (spec 06 CA-3).
     * @throws ApiError
     */
    public getJobEventsApiV1JobsJobIdEventsGet(
        jobId: string,
    ): Observable<any> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/api/v1/jobs/{job_id}/events',
            path: {
                'job_id': jobId,
            },
            errors: {
                404: `Not Found`,
                422: `Validation Error`,
            },
        });
    }
}
