import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { TranslocoPipe } from '@jsverse/transloco';

/**
 * Placeholder de pantalla para features que todavía no se implementan (M4 scaffold).
 * Las próximas rondas reemplazan el componente de ruta que usa esto, no este archivo
 * en sí: se deja como pieza compartida por si a futuro hace falta un estado similar
 * (p. ej. una sección de una pantalla real que depende de un endpoint aún no listo).
 */
@Component({
  selector: 'app-coming-soon',
  imports: [MatCardModule, TranslocoPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-card class="m-4 max-w-xl">
      <mat-card-header>
        <mat-card-title>{{ titleKey() | transloco }}</mat-card-title>
      </mat-card-header>
      <mat-card-content>
        <p>{{ 'common.underConstruction' | transloco }}</p>
      </mat-card-content>
    </mat-card>
  `,
})
export class ComingSoonComponent {
  readonly titleKey = input.required<string>();
}
