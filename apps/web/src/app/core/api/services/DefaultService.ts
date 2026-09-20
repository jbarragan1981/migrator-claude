/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import type { Observable } from 'rxjs';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
@Injectable({
    providedIn: 'root',
})
export class DefaultService {
    constructor(public readonly http: HttpClient) {}
    /**
     * Health
     * @returns string Successful Response
     * @throws ApiError
     */
    public healthHealthGet(): Observable<Record<string, string>> {
        return __request(OpenAPI, this.http, {
            method: 'GET',
            url: '/health',
        });
    }
}
