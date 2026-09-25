import type { AndroidUiNode } from '../../../types/android-debug'

export interface CompressedHierarchyRow {
  id: string
  chain: AndroidUiNode[]
  terminalNodeId: string
  children: CompressedHierarchyRow[]
}

export interface HierarchyCompressionOptions {
  compress?: boolean
  includeNode?: (node: AndroidUiNode) => boolean
}

function meaningful(value: string | null): boolean {
  return Boolean(value?.trim())
}

function hasNormalBounds(node: AndroidUiNode): boolean {
  const { left, top, right, bottom } = node.bounds
  return (
    [left, top, right, bottom].every(Number.isFinite) && right > left && bottom > top
  )
}

function isWebView(node: AndroidUiNode): boolean {
  return node.class_name?.split('.').at(-1)?.toLocaleLowerCase() === 'webview'
}

export function isActionableUiNode(node: AndroidUiNode): boolean {
  return node.clickable || node.scrollable || node.editable || node.checkable
}

export function isMeaningfulUiNode(node: AndroidUiNode): boolean {
  return meaningful(node.text) || meaningful(node.content_description)
}

function canContinueFrom(node: AndroidUiNode): boolean {
  return (
    !isActionableUiNode(node) &&
    !isMeaningfulUiNode(node) &&
    !isWebView(node) &&
    hasNormalBounds(node)
  )
}

function canJoinChild(node: AndroidUiNode): boolean {
  // WebView is included as the terminal breadcrumb, but its descendants start
  // new rows. Other meaningful/actionable nodes remain independently visible.
  return !isActionableUiNode(node) && !isMeaningfulUiNode(node) && hasNormalBounds(node)
}

export function buildCompressedHierarchy(
  root: AndroidUiNode,
  options: HierarchyCompressionOptions = {},
): CompressedHierarchyRow {
  const compress = options.compress ?? true
  const includeNode = options.includeNode ?? (() => true)

  const build = (start: AndroidUiNode): CompressedHierarchyRow => {
    const chain = [start]
    let terminal = start

    while (compress && canContinueFrom(terminal)) {
      const relevantChildren = (terminal.children ?? []).filter(includeNode)
      if (relevantChildren.length !== 1) break
      const child = relevantChildren[0]
      if (!child || !canJoinChild(child)) break
      chain.push(child)
      terminal = child
    }

    const children = (terminal.children ?? [])
      .filter(includeNode)
      .map((child) => build(child))
    return {
      id: chain.map((node) => node.node_id).join('>'),
      chain,
      terminalNodeId: terminal.node_id,
      children,
    }
  }

  return build(root)
}

export function countCompressedRows(row: CompressedHierarchyRow): number {
  return (
    1 + row.children.reduce((total, child) => total + countCompressedRows(child), 0)
  )
}
