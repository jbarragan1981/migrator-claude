import { OutputTreeEntry } from '../../core/api/models/OutputTreeEntry';
import { buildOutputTree, filterTree, flattenTree } from './result-tree';

function entry(path: string, kind: OutputTreeEntry.kind = OutputTreeEntry.kind.FILE, size: number | null = 10): OutputTreeEntry {
  return { path, kind, size };
}

describe('buildOutputTree', () => {
  it('agrupa las rutas planas en un árbol de carpetas y archivos', () => {
    const entries: OutputTreeEntry[] = [
      entry('README.md'),
      entry('conversations', OutputTreeEntry.kind.DIR, null),
      entry('conversations/2026', OutputTreeEntry.kind.DIR, null),
      entry('conversations/2026/2026-01-01_hola_ab12cd34.md'),
      entry('memories', OutputTreeEntry.kind.DIR, null),
      entry('memories/profile.md'),
    ];

    const tree = buildOutputTree(entries);

    expect(tree.map((node) => node.name)).toEqual(['conversations', 'memories', 'README.md']);

    const conversations = tree.find((node) => node.name === 'conversations');
    expect(conversations?.kind).toBe('dir');
    expect(conversations?.children.map((node) => node.name)).toEqual(['2026']);
    expect(conversations?.children[0]?.children.map((node) => node.name)).toEqual([
      '2026-01-01_hola_ab12cd34.md',
    ]);

    const memories = tree.find((node) => node.name === 'memories');
    expect(memories?.children.map((node) => node.name)).toEqual(['profile.md']);
  });

  it('reconstruye carpetas intermedias aunque el backend no las liste explícitamente', () => {
    const entries: OutputTreeEntry[] = [entry('projects/mi-proyecto/docs/notas.md')];

    const tree = buildOutputTree(entries);

    expect(tree).toHaveLength(1);
    expect(tree[0].name).toBe('projects');
    expect(tree[0].kind).toBe('dir');
    expect(tree[0].children[0].name).toBe('mi-proyecto');
    expect(tree[0].children[0].children[0].name).toBe('docs');
    expect(tree[0].children[0].children[0].children[0].name).toBe('notas.md');
  });

  it('ordena carpetas antes que archivos, y alfabéticamente dentro de cada grupo', () => {
    const entries: OutputTreeEntry[] = [entry('b.md'), entry('a.md'), entry('zeta', OutputTreeEntry.kind.DIR, null)];

    const tree = buildOutputTree(entries);

    expect(tree.map((node) => node.name)).toEqual(['zeta', 'a.md', 'b.md']);
  });
});

describe('filterTree', () => {
  const tree = buildOutputTree([
    entry('memories', OutputTreeEntry.kind.DIR, null),
    entry('memories/profile.md'),
    entry('memories/people/ana.md'),
    entry('README.md'),
  ]);

  it('sin búsqueda devuelve el árbol completo', () => {
    expect(filterTree(tree, '')).toBe(tree);
  });

  it('conserva solo los archivos que matchean por nombre y sus carpetas ancestras', () => {
    const filtered = filterTree(tree, 'ana');

    expect(filtered.map((node) => node.name)).toEqual(['memories']);
    const memories = filtered[0];
    expect(memories.children.map((node) => node.name)).toEqual(['people']);
    expect(memories.children[0].children.map((node) => node.name)).toEqual(['ana.md']);
  });

  it('si una carpeta matchea por nombre, conserva todo su contenido original', () => {
    const filtered = filterTree(tree, 'memories');

    expect(filtered).toHaveLength(1);
    expect(filtered[0].children.map((node) => node.name).sort()).toEqual(['people', 'profile.md']);
  });

  it('sin coincidencias devuelve un árbol vacío', () => {
    expect(filterTree(tree, 'no-existe')).toEqual([]);
  });
});

describe('flattenTree', () => {
  it('aplana el árbol en filas con su profundidad, en orden de aparición', () => {
    const tree = buildOutputTree([
      entry('memories', OutputTreeEntry.kind.DIR, null),
      entry('memories/profile.md'),
      entry('README.md'),
    ]);

    const rows = flattenTree(tree);

    expect(rows.map((row) => [row.node.name, row.depth])).toEqual([
      ['memories', 0],
      ['profile.md', 1],
      ['README.md', 0],
    ]);
  });
});
