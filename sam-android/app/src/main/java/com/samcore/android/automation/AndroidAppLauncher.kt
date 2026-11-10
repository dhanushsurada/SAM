package com.samcore.android.automation

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Log

/**
 * Handles intent-based application launching, web browsing, and sharing.
 */
class AndroidAppLauncher(private val context: Context) {

    fun launchAppByNameOrPackage(appNameOrPkg: String): Boolean {
        val pm = context.packageManager

        // 1. Direct package match
        val directIntent = pm.getLaunchIntentForPackage(appNameOrPkg)
        if (directIntent != null) {
            directIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(directIntent)
            return true
        }

        // 2. Search installed applications by display label
        val targetLower = appNameOrPkg.trim().lowercase()
        val installedApps = pm.getInstalledApplications(PackageManager.GET_META_DATA)

        for (app in installedApps) {
            val label = pm.getApplicationLabel(app).toString().lowercase()
            if (label == targetLower || label.contains(targetLower)) {
                val launchIntent = pm.getLaunchIntentForPackage(app.packageName)
                if (launchIntent != null) {
                    launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(launchIntent)
                    return true
                }
            }
        }

        Log.w(TAG, "Application '$appNameOrPkg' could not be resolved on device")
        return false
    }

    fun openUrl(url: String): Boolean {
        return try {
            val validUrl = if (!url.startsWith("http://") && !url.startsWith("https://")) {
                "https://$url"
            } else url
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(validUrl)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to open URL $url: ${e.message}", e)
            false
        }
    }

    fun shareContent(text: String, title: String = "Share"): Boolean {
        return try {
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, text)
                putExtra(Intent.EXTRA_TITLE, title)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            val chooser = Intent.createChooser(intent, title).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(chooser)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to share content: ${e.message}", e)
            false
        }
    }

    companion object {
        private const val TAG = "AndroidAppLauncher"
    }
}
