package com.tapbot.agent.state

import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicReference

data class InsetsState(
    val top: Int = 0,
    val bottom: Int = 0,
    val left: Int = 0,
    val right: Int = 0,
)

data class DisplayState(
    val physicalWidth: Int = 0,
    val physicalHeight: Int = 0,
    val logicalWidth: Int = 0,
    val logicalHeight: Int = 0,
    val density: Float = 1f,
    val densityDpi: Int = 160,
    val rotation: Int = 0,
    val insets: InsetsState = InsetsState(),
)

data class AgentState(
    val remoteControlEnabled: Boolean = false,
    val accessibilityEnabled: Boolean = false,
    val captureReady: Boolean = false,
    val streamRunning: Boolean = false,
    val serverRunning: Boolean = false,
    val serverPort: Int = 8765,
    val connectedClients: Int = 0,
    val frameId: Long? = null,
    val capturedAtMs: Long? = null,
    val display: DisplayState = DisplayState(),
    val lastError: String? = null,
)

object AgentStateStore {
    private val value = AtomicReference(AgentState())
    private val listeners = CopyOnWriteArrayList<(AgentState) -> Unit>()

    fun snapshot(): AgentState = value.get()

    fun update(transform: (AgentState) -> AgentState): AgentState {
        while (true) {
            val current = value.get()
            val next = transform(current)
            if (value.compareAndSet(current, next)) {
                listeners.forEach { it(next) }
                return next
            }
        }
    }

    fun addListener(listener: (AgentState) -> Unit) {
        listeners += listener
        listener(snapshot())
    }

    fun removeListener(listener: (AgentState) -> Unit) {
        listeners -= listener
    }
}
