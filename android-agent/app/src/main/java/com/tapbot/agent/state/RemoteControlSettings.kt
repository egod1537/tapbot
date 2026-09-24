package com.tapbot.agent.state

import android.content.Context

class RemoteControlSettings(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun isEnabled(): Boolean = preferences.getBoolean(KEY_ENABLED, false)

    fun setEnabled(enabled: Boolean) {
        preferences.edit().putBoolean(KEY_ENABLED, enabled).apply()
    }

    companion object {
        private const val PREFERENCES = "tapbot_agent_control"
        private const val KEY_ENABLED = "remote_control_enabled"
    }
}
