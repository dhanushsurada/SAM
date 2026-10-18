package com.samcore.android.notifications

import android.content.Context
import com.samcore.android.data.transport.TaskSnapshot

/**
 * Extracted so TaskMonitor can be unit-tested (TaskMonitorTest) with a fake
 * that just records calls, instead of needing a real Android Context/
 * NotificationManager. AndroidTaskNotifier is the real implementation, still
 * backed by the existing SamNotifications object — no behavior change, pure
 * seam for testability.
 */
interface TaskNotifier {
    fun notifyFinished(snapshot: TaskSnapshot)
}

class AndroidTaskNotifier(context: Context) : TaskNotifier {
    private val appContext = context.applicationContext

    override fun notifyFinished(snapshot: TaskSnapshot) {
        SamNotifications.notifyTaskFinished(appContext, snapshot)
    }
}
