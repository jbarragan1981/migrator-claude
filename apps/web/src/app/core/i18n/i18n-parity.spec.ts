import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * spec 07 CA-3: "Cambiar idioma traduce el 100% de los textos visibles (test que
 * compara claves de es.json y en.json)". Lee los dos archivos REALES servidos como
 * assets (public/assets/i18n/, Angular 21 sirve `public/` como raíz estática) y
 * falla si un idioma tiene una clave que al otro le falta, en cualquier nivel de
 * anidamiento. Cada feature que agregue una clave nueva la agrega en AMBOS
 * archivos en el mismo commit (CLAUDE.md); este test es la red de seguridad.
 */

interface TranslationTree {
  [key: string]: string | TranslationTree;
}

function collectKeys(node: TranslationTree, prefix = ''): string[] {
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === 'string' ? [path] : collectKeys(value, path);
  });
}

function readTranslation(lang: 'es' | 'en'): TranslationTree {
  const here = dirname(fileURLToPath(import.meta.url));
  const path = join(here, '..', '..', '..', '..', 'public', 'assets', 'i18n', `${lang}.json`);
  return JSON.parse(readFileSync(path, 'utf-8')) as TranslationTree;
}

describe('i18n es/en parity (spec 07 CA-3)', () => {
  it('es.json and en.json expose exactly the same set of keys', () => {
    const esKeys = collectKeys(readTranslation('es')).sort();
    const enKeys = collectKeys(readTranslation('en')).sort();
    expect(esKeys).toEqual(enKeys);
  });

  it('has at least the base layout keys (app.title, nav.*)', () => {
    const esKeys = collectKeys(readTranslation('es'));
    expect(esKeys).toEqual(
      expect.arrayContaining([
        'app.title',
        'nav.upload',
        'nav.inventory',
        'nav.convert',
        'nav.result',
        'nav.settings',
      ]),
    );
  });
});
