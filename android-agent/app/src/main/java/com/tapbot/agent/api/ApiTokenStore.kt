package com.tapbot.agent.api

import android.content.Context
import android.util.Base64
import java.security.SecureRandom

class ApiTokenStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun getOrCreate(): String {
        preferences.getString(KEY_TOKEN, null)?.let { return it }
        val bytes = ByteArray(32).also(SecureRandom()::nextBytes)
        val token = Base64.encodeToString(
            bytes,
            Base64.NO_WRAP or Base64.NO_PADDING or Base64.URL_SAFE,
        )
        preferences.edit().putString(KEY_TOKEN, token).apply()
        return token
    }

    fun rotate(): String {
        preferences.edit().remove(KEY_TOKEN).apply()
        return getOrCreate()
    }

    companion object {
        private const val PREFERENCES = "tapbot_agent_security"
        private const val KEY_TOKEN = "api_token"
    }
}
