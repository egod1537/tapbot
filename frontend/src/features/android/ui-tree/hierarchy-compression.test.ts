import { describe, expect, it } from 'vitest'
import type { AndroidUiNode } from '../../../types/android-debug'
import { buildCompressedHierarchy, countCompressedRows } from './hierarchy-compression'

function uiNode(id: string, overrides: Partial<AndroidUiNode> = {}): AndroidUiNode {
  return {
    node_id: id,
    parent_id: null,
    depth: 0,
    class_name: 'android.widget.FrameLayout',
    text: null,
    content_description: null,
    view_id_resource_name: null,
    package_name: 'example',
    bounds: { left: 0, top: 0, right: 100, bottom: 100 },
    clickable: false,
    enabled: true,
    focusable: false,
    focused: false,
    selected: false,
    checked: false,
    checkable: false,
    scrollable: false,
    editable: false,
    visible_to_user: true,
    password: false,
    child_count: 0,
    children: [],
    ...overrides,
  }
}

function attach(parent: AndroidUiNode, ...children: AndroidUiNode[]) {
  parent.children = children
  parent.child_count = children.length
  for (const child of children) {
    child.parent_id = parent.node_id
    child.depth = parent.depth + 1
  }
  return parent
}

describe('UI tree hierarchy compression', () => {
  it('compresses a single-child wrapper chain before a branch', () => {
    const n1 = uiNode('n1')
    const n2 = uiNode('n2', { class_name: 'android.widget.LinearLayout' })
    const n3 = uiNode('n3')
    const n4 = uiNode('n4', { class_name: 'android.webkit.WebView' })
    const n5 = uiNode('n5', { text: 'Reserve', clickable: true })
    const n6 = uiNode('n6', { text: 'Cancel', clickable: true })
    attach(n4, n5, n6)
    attach(n3, n4)
    attach(n2, n3)
    attach(n1, n2)

    const result = buildCompressedHierarchy(n1)

    expect(result.chain.map((node) => node.node_id)).toEqual(['n1', 'n2', 'n3', 'n4'])
    expect(result.terminalNodeId).toBe('n4')
    expect(result.children.map((row) => row.chain[0]?.node_id)).toEqual(['n5', 'n6'])
    expect(countCompressedRows(result)).toBe(3)
  })

  it.each([
    ['clickable', { clickable: true }],
    ['scrollable', { scrollable: true }],
    ['editable', { editable: true }],
    ['checkable', { checkable: true }],
    ['text', { text: 'Photo verification' }],
    ['description', { content_description: 'Back' }],
    ['zero-area bounds', { bounds: { left: 0, top: 0, right: 0, bottom: 0 } }],
  ] as const)('stops before a meaningful %s node', (_, overrides) => {
    const root = uiNode('root')
    const boundary = uiNode('boundary', overrides)
    const leaf = uiNode('leaf')
    attach(boundary, leaf)
    attach(root, boundary)

    const result = buildCompressedHierarchy(root)

    expect(result.chain.map((node) => node.node_id)).toEqual(['root'])
    expect(result.children[0]?.chain[0]?.node_id).toBe('boundary')
  })

  it('includes WebView as the terminal segment and keeps its descendants separate', () => {
    const root = uiNode('root')
    const wrapper = uiNode('wrapper')
    const webView = uiNode('webview', { class_name: 'android.webkit.WebView' })
    const domNode = uiNode('dom', { class_name: 'android.view.View' })
    attach(webView, domNode)
    attach(wrapper, webView)
    attach(root, wrapper)

    const result = buildCompressedHierarchy(root)

    expect(result.chain.map((node) => node.node_id)).toEqual([
      'root',
      'wrapper',
      'webview',
    ])
    expect(result.children[0]?.chain[0]?.node_id).toBe('dom')
  })

  it('keeps one original node per row when compression is disabled', () => {
    const root = uiNode('root')
    const middle = uiNode('middle')
    const leaf = uiNode('leaf')
    attach(middle, leaf)
    attach(root, middle)

    const result = buildCompressedHierarchy(root, { compress: false })

    expect(result.chain).toHaveLength(1)
    expect(result.children[0]?.chain).toHaveLength(1)
    expect(result.children[0]?.children[0]?.chain).toHaveLength(1)
    expect(countCompressedRows(result)).toBe(3)
  })

  it('compresses only nodes retained by a hierarchy filter', () => {
    const root = uiNode('root')
    const wrapper = uiNode('wrapper')
    const ignored = uiNode('ignored')
    const action = uiNode('action', { clickable: true, text: 'Select' })
    attach(wrapper, ignored, action)
    attach(root, wrapper)
    const retained = new Set(['root', 'wrapper', 'action'])

    const result = buildCompressedHierarchy(root, {
      includeNode: (node) => retained.has(node.node_id),
    })

    expect(result.chain.map((node) => node.node_id)).toEqual(['root', 'wrapper'])
    expect(result.children.map((row) => row.chain[0]?.node_id)).toEqual(['action'])
  })
})
