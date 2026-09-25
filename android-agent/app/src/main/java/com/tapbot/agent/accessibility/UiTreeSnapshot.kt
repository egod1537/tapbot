package com.tapbot.agent.accessibility

data class UiBounds(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
)

data class UiNodeSnapshot(
    val nodeId: String,
    val parentId: String?,
    val depth: Int,
    val className: String?,
    val text: String?,
    val contentDescription: String?,
    val viewIdResourceName: String?,
    val packageName: String?,
    val bounds: UiBounds,
    val clickable: Boolean,
    val enabled: Boolean,
    val focusable: Boolean,
    val focused: Boolean,
    val selected: Boolean,
    val checked: Boolean,
    val checkable: Boolean,
    val scrollable: Boolean,
    val editable: Boolean,
    val visibleToUser: Boolean,
    val password: Boolean,
    val childCount: Int,
    val children: List<UiNodeSnapshot>,
)

data class UiTreeSnapshot(
    val capturedAt: String,
    val packageName: String?,
    val windowTitle: String?,
    val rotation: Int,
    val screenWidth: Int,
    val screenHeight: Int,
    val root: UiNodeSnapshot,
    val nodes: List<UiNodeSnapshot>,
    val truncated: Boolean,
)

data class UiTreeMetadata(
    val capturedAt: String,
    val windowTitle: String?,
    val rotation: Int,
    val screenWidth: Int,
    val screenHeight: Int,
)

/** Minimal platform-neutral view used by JVM tests and the Android node adapter. */
interface UiNodeSource {
    val className: String?
    val text: String?
    val contentDescription: String?
    val viewIdResourceName: String?
    val packageName: String?
    val bounds: UiBounds
    val clickable: Boolean
    val enabled: Boolean
    val focusable: Boolean
    val focused: Boolean
    val selected: Boolean
    val checked: Boolean
    val checkable: Boolean
    val scrollable: Boolean
    val editable: Boolean
    val visibleToUser: Boolean
    val password: Boolean
    val childCount: Int

    fun child(index: Int): UiNodeSource?

    fun recycle()
}

class UiTreeSnapshotter(
    private val maxNodes: Int = DEFAULT_MAX_NODES,
    private val maxDepth: Int = DEFAULT_MAX_DEPTH,
    private val maxTextLength: Int = DEFAULT_MAX_TEXT_LENGTH,
) {
    init {
        require(maxNodes > 0) { "maxNodes must be positive" }
        require(maxDepth >= 0) { "maxDepth must not be negative" }
        require(maxTextLength > 0) { "maxTextLength must be positive" }
    }

    fun snapshot(root: UiNodeSource?, metadata: UiTreeMetadata): UiTreeSnapshot? {
        if (root == null) return null
        val flatNodes = mutableListOf<UiNodeSnapshot?>()
        var truncated = false

        fun visit(
            source: UiNodeSource,
            nodeId: String,
            parentId: String?,
            depth: Int,
        ): UiNodeSnapshot? {
            try {
                if (flatNodes.size >= maxNodes) {
                    truncated = true
                    return null
                }
                val rawChildCount = source.childCount.coerceAtLeast(0)
                val flatIndex = flatNodes.size
                flatNodes += null
                val children = mutableListOf<UiNodeSnapshot>()
                if (depth >= maxDepth) {
                    if (rawChildCount > 0) truncated = true
                } else {
                    for (index in 0 until rawChildCount) {
                        if (flatNodes.size >= maxNodes) {
                            truncated = true
                            break
                        }
                        val childResult = runCatching { source.child(index) }
                        if (childResult.isFailure) {
                            truncated = true
                            continue
                        }
                        val child = childResult.getOrNull() ?: continue
                        visit(child, "$nodeId.$index", nodeId, depth + 1)?.let(children::add)
                    }
                }
                val snapshot = UiNodeSnapshot(
                    nodeId = nodeId,
                    parentId = parentId,
                    depth = depth,
                    className = clip(source.className),
                    text = if (source.password) null else clip(source.text),
                    contentDescription = clip(source.contentDescription),
                    viewIdResourceName = clip(source.viewIdResourceName),
                    packageName = clip(source.packageName),
                    bounds = source.bounds,
                    clickable = source.clickable,
                    enabled = source.enabled,
                    focusable = source.focusable,
                    focused = source.focused,
                    selected = source.selected,
                    checked = source.checked,
                    checkable = source.checkable,
                    scrollable = source.scrollable,
                    editable = source.editable,
                    visibleToUser = source.visibleToUser,
                    password = source.password,
                    childCount = rawChildCount,
                    children = children.toList(),
                )
                flatNodes[flatIndex] = snapshot
                return snapshot
            } finally {
                source.recycle()
            }
        }

        val rootSnapshot = visit(root, "n0", null, 0) ?: return null
        return UiTreeSnapshot(
            capturedAt = metadata.capturedAt,
            packageName = rootSnapshot.packageName,
            windowTitle = clip(metadata.windowTitle),
            rotation = metadata.rotation,
            screenWidth = metadata.screenWidth,
            screenHeight = metadata.screenHeight,
            root = rootSnapshot,
            nodes = flatNodes.filterNotNull(),
            truncated = truncated,
        )
    }

    private fun clip(value: String?): String? = value?.take(maxTextLength)

    companion object {
        const val DEFAULT_MAX_NODES = 2_000
        const val DEFAULT_MAX_DEPTH = 50
        const val DEFAULT_MAX_TEXT_LENGTH = 512
    }
}
