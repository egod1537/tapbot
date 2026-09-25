package com.tapbot.agent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UiTreeSnapshotterTest {
    private val metadata = UiTreeMetadata(
        capturedAt = "2026-09-25T00:00:00Z",
        windowTitle = "Settings",
        rotation = 0,
        screenWidth = 1080,
        screenHeight = 2400,
    )

    @Test
    fun serializesTreeFieldsBoundsAndEmptyChildren() {
        val child = FakeNode(
            className = "android.widget.Button",
            text = "사진 인증",
            contentDescription = "Verify photo",
            viewIdResourceName = "com.example:id/verifyButton",
            bounds = UiBounds(220, 1680, 860, 1820),
            clickable = true,
            enabled = true,
        )
        val root = FakeNode(
            className = "android.widget.FrameLayout",
            packageName = "com.example.app",
            bounds = UiBounds(0, 0, 1080, 2400),
            children = listOf(child),
        )

        val tree = UiTreeSnapshotter().snapshot(root, metadata)!!

        assertEquals("com.example.app", tree.packageName)
        assertEquals(2, tree.nodes.size)
        assertEquals("n0.0", child.recycledNodeId(tree))
        assertEquals("Verify photo", tree.root.children.single().contentDescription)
        assertEquals("com.example:id/verifyButton", tree.root.children.single().viewIdResourceName)
        assertEquals(UiBounds(220, 1680, 860, 1820), tree.root.children.single().bounds)
        assertTrue(tree.root.children.single().clickable)
        assertTrue(tree.root.children.single().children.isEmpty())
        assertTrue(root.recycled)
        assertTrue(child.recycled)
        assertFalse(tree.truncated)
    }

    @Test
    fun redactsPasswordTextAndClipsLargeText() {
        val password = FakeNode(text = "secret", password = true)
        val longText = FakeNode(text = "abcdefgh")
        val tree = UiTreeSnapshotter(maxTextLength = 4).snapshot(
            FakeNode(children = listOf(password, longText)),
            metadata,
        )!!

        assertNull(tree.nodes[1].text)
        assertEquals("abcd", tree.nodes[2].text)
    }

    @Test
    fun truncatesAtNodeAndDepthLimitsWithoutFailingSnapshot() {
        val nodeLimited = UiTreeSnapshotter(maxNodes = 2).snapshot(
            FakeNode(children = listOf(FakeNode(), FakeNode())),
            metadata,
        )!!
        assertEquals(2, nodeLimited.nodes.size)
        assertTrue(nodeLimited.truncated)

        val depthLimited = UiTreeSnapshotter(maxDepth = 0).snapshot(
            FakeNode(children = listOf(FakeNode())),
            metadata,
        )!!
        assertEquals(1, depthLimited.nodes.size)
        assertTrue(depthLimited.root.children.isEmpty())
        assertTrue(depthLimited.truncated)
    }

    @Test
    fun returnsNullWhenRootIsUnavailable() {
        assertNull(UiTreeSnapshotter().snapshot(null, metadata))
    }

    @Test
    fun malformedChildDoesNotFailTheWholeSnapshot() {
        val tree = UiTreeSnapshotter().snapshot(
            FakeNode(children = listOf(FakeNode()), failingChildIndex = 0),
            metadata,
        )!!

        assertEquals(1, tree.nodes.size)
        assertTrue(tree.truncated)
    }

    private fun FakeNode.recycledNodeId(tree: UiTreeSnapshot): String {
        assertTrue(recycled)
        return tree.nodes.first { it.text == text }.nodeId
    }
}

private class FakeNode(
    override val className: String? = null,
    override val text: String? = null,
    override val contentDescription: String? = null,
    override val viewIdResourceName: String? = null,
    override val packageName: String? = null,
    override val bounds: UiBounds = UiBounds(0, 0, 1, 1),
    override val clickable: Boolean = false,
    override val enabled: Boolean = true,
    override val focusable: Boolean = false,
    override val focused: Boolean = false,
    override val selected: Boolean = false,
    override val checked: Boolean = false,
    override val checkable: Boolean = false,
    override val scrollable: Boolean = false,
    override val editable: Boolean = false,
    override val visibleToUser: Boolean = true,
    override val password: Boolean = false,
    private val children: List<FakeNode> = emptyList(),
    private val failingChildIndex: Int? = null,
) : UiNodeSource {
    var recycled = false

    override val childCount: Int get() = children.size

    override fun child(index: Int): UiNodeSource {
        if (index == failingChildIndex) error("malformed child")
        return children[index]
    }

    override fun recycle() {
        recycled = true
    }
}
