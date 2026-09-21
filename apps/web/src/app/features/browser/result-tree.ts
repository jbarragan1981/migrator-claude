import type { OutputTreeEntry } from '../../core/api/models/OutputTreeEntry';

/**
 * `GET /exports/{id}/output/tree` (spec 06) devuelve una LISTA PLANA de rutas
 * relativas POSIX (`OutputTreeResponse.entries`, ver el docstring de
 * `OutputTreeEntry` en el cliente generado). El árbol de la pantalla 4 se
 * reconstruye acá, partiendo cada `path` por `/` — el backend no necesita modelar
 * un schema recursivo para esto (encargo de la tarea).
 */
export interface TreeNode {
  name: string;
  path: string;
  kind: 'file' | 'dir';
  size: number | null;
  children: TreeNode[];
}

function parentPathOf(path: string): string | null {
  const lastSlash = path.lastIndexOf('/');
  return lastSlash === -1 ? null : path.slice(0, lastSlash);
}

function nameOf(path: string): string {
  const lastSlash = path.lastIndexOf('/');
  return lastSlash === -1 ? path : path.slice(lastSlash + 1);
}

/**
 * Arma el árbol a partir de la lista plana. Reconstruye carpetas intermedias por
 * las que pasa un archivo aunque el backend no las hubiera listado explícitamente
 * (robusto a esa variación, sin depender de que TODA carpeta intermedia venga
 * como una entrada `kind: "dir"` propia).
 */
export function buildOutputTree(entries: OutputTreeEntry[]): TreeNode[] {
  const nodesByPath = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  const attach = (node: TreeNode): void => {
    const parentPath = parentPathOf(node.path);
    if (parentPath === null) {
      roots.push(node);
      return;
    }
    const parent = ensureDir(parentPath);
    parent.children.push(node);
  };

  function ensureDir(path: string): TreeNode {
    const existing = nodesByPath.get(path);
    if (existing) {
      return existing;
    }
    const node: TreeNode = { name: nameOf(path), path, kind: 'dir', size: null, children: [] };
    nodesByPath.set(path, node);
    attach(node);
    return node;
  }

  const sorted = [...entries].sort((a, b) => a.path.localeCompare(b.path));
  for (const entry of sorted) {
    if (entry.kind === 'dir') {
      ensureDir(entry.path);
      continue;
    }
    if (nodesByPath.has(entry.path)) {
      continue;
    }
    const node: TreeNode = {
      name: nameOf(entry.path),
      path: entry.path,
      kind: 'file',
      size: entry.size ?? null,
      children: [],
    };
    nodesByPath.set(entry.path, node);
    attach(node);
  }

  sortTree(roots);
  return roots;
}

function sortTree(nodes: TreeNode[]): void {
  nodes.sort((a, b) => {
    if (a.kind !== b.kind) {
      return a.kind === 'dir' ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });
  for (const node of nodes) {
    sortTree(node.children);
  }
}

/** Una fila ya "aplanada" del árbol, con su profundidad, para renderizar sin
 * componentes recursivos (una `<ul>` con indentación por `depth` alcanza para lo
 * que pide spec 07 pantalla 4 — no hace falta expandir/colapsar carpetas). */
export interface FlatTreeRow {
  node: TreeNode;
  depth: number;
}

export function flattenTree(nodes: TreeNode[], depth = 0): FlatTreeRow[] {
  const rows: FlatTreeRow[] = [];
  for (const node of nodes) {
    rows.push({ node, depth });
    if (node.children.length > 0) {
      rows.push(...flattenTree(node.children, depth + 1));
    }
  }
  return rows;
}

/**
 * Filtra el árbol por nombre (spec 07 pantalla 4: "búsqueda por título"). Una
 * carpeta se conserva si su propio nombre matchea (con TODOS sus hijos
 * originales) o si al menos uno de sus descendientes matchea (solo esos).
 */
export function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return nodes;
  }
  const result: TreeNode[] = [];
  for (const node of nodes) {
    const nameMatches = node.name.toLowerCase().includes(trimmed);
    if (node.kind === 'file') {
      if (nameMatches) {
        result.push(node);
      }
      continue;
    }
    if (nameMatches) {
      result.push(node);
      continue;
    }
    const filteredChildren = filterTree(node.children, query);
    if (filteredChildren.length > 0) {
      result.push({ ...node, children: filteredChildren });
    }
  }
  return result;
}
