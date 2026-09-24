package com.tapbot.agent.system

import android.os.Build
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.Collections

data class DeviceInfo(
    val manufacturer: String,
    val model: String,
    val androidVersion: String,
    val sdkInt: Int,
    val localIpv4Addresses: List<String>,
)

object DeviceInfoProvider {
    fun current(): DeviceInfo = DeviceInfo(
        manufacturer = Build.MANUFACTURER,
        model = Build.MODEL,
        androidVersion = Build.VERSION.RELEASE,
        sdkInt = Build.VERSION.SDK_INT,
        localIpv4Addresses = localIpv4Addresses(),
    )

    private fun localIpv4Addresses(): List<String> = runCatching {
        Collections.list(NetworkInterface.getNetworkInterfaces())
            .asSequence()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { Collections.list(it.inetAddresses).asSequence() }
            .filterIsInstance<Inet4Address>()
            .filterNot { it.isLoopbackAddress }
            .mapNotNull { it.hostAddress }
            .sorted()
            .toList()
    }.getOrDefault(emptyList())
}
