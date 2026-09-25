package com.tapbot.agent.accessibility

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo

class AccessibilityNodeSource(
    private val node: AccessibilityNodeInfo,
) : UiNodeSource {
    override val className: String? get() = node.className?.toString()
    override val text: String? get() = node.text?.toString()
    override val contentDescription: String? get() = node.contentDescription?.toString()
    override val viewIdResourceName: String? get() = node.viewIdResourceName
    override val packageName: String? get() = node.packageName?.toString()
    override val bounds: UiBounds
        get() = Rect().also(node::getBoundsInScreen).let {
            UiBounds(it.left, it.top, it.right, it.bottom)
        }
    override val clickable: Boolean get() = node.isClickable
    override val enabled: Boolean get() = node.isEnabled
    override val focusable: Boolean get() = node.isFocusable
    override val focused: Boolean get() = node.isFocused
    override val selected: Boolean get() = node.isSelected
    override val checked: Boolean get() = node.isChecked
    override val checkable: Boolean get() = node.isCheckable
    override val scrollable: Boolean get() = node.isScrollable
    override val editable: Boolean get() = node.isEditable
    override val visibleToUser: Boolean get() = node.isVisibleToUser
    override val password: Boolean get() = node.isPassword
    override val childCount: Int get() = node.childCount

    override fun child(index: Int): UiNodeSource? =
        node.getChild(index)?.let(::AccessibilityNodeSource)

    @Suppress("DEPRECATION")
    override fun recycle() {
        node.recycle()
    }
}
