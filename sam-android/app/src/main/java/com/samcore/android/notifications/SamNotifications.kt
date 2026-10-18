package com.samcore.android.notifications

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.samcore.android.R
import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.data.transport.TaskStatus

/**
 * Deliberately narrow: one channel, one notification type ("a task you sent
 * finished"). PDR §13/§18: "every capability must be permission-aware" and
 * "do not fake native OS capabilities" — this checks POST_NOTIFICATIONS
 * itself before ever calling notify(), rather than assuming the manifest
 * declaration or an earlier request means it's actually granted right now
 * (the user can revoke it in system Settings at any time).
 *
 * Scope note (see the build report / README): the completion notification
 * fires whenever TaskMonitor is watching a task and it reaches a terminal
 * state. TaskMonitor runs on an application-scoped coroutine, so this
 * survives navigating between screens. While a watch is active the app also
 * asks for a foreground service (TaskWatchForegroundService) to make it much
 * less likely that Android freezes or kills the process mid-task — that is a
 * best-effort priority boost, NOT a guarantee: nothing is persisted, so if the
 * process is killed anyway (OEM battery managers can do this even to
 * foreground services) the watch is simply lost and no completion
 * notification is posted. Not verified on a real device yet.
 *
 * Two channels, deliberately separate so the user can silence one without the
 * other: "Task updates" (completion, default importance) and "Task in
 * progress" (the foreground service's ongoing notification, low importance —
 * no sound, no heads-up).
 */
object SamNotifications {
    const val CHANNEL_ID = "sam_task_updates"
    const val CHANNEL_ID_FOREGROUND = "sam_task_in_progress"
    private const val NOTIFICATION_ID_BASE = 1000

    /** Fixed id for the foreground service's one ongoing notification. */
    const val ONGOING_NOTIFICATION_ID = 2000

    /** Idempotent — creating a channel that already exists is a no-op. */
    fun ensureChannel(context: Context) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val updates = NotificationChannel(
            CHANNEL_ID,
            "Task updates",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "Lets you know when a task you sent SAM finishes."
        }
        manager.createNotificationChannel(updates)

        val inProgress = NotificationChannel(
            CHANNEL_ID_FOREGROUND,
            "Task in progress",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Shown while the app keeps its connection to SAM Core open for a task you sent."
        }
        manager.createNotificationChannel(inProgress)
    }

    /**
     * The foreground service's ongoing notification. Deliberately generic — it
     * does NOT include the task's instruction text: a task can be private, and
     * this notification can sit on the lock screen for as long as the task
     * runs. (The completion notification below does show the result/instruction
     * text; that is pre-existing behavior, left unchanged here.)
     *
     * No contentIntent yet, so tapping it does nothing — same gap as the
     * completion notification; listed in the README's not-yet list.
     */
    fun buildOngoingNotification(context: Context): Notification =
        NotificationCompat.Builder(context, CHANNEL_ID_FOREGROUND)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("SAM is working on your task")
            .setContentText("Keeping the connection to SAM Core open until it finishes.")
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW) // pre-O only; on O+ the channel's importance rules
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()

    fun notifyTaskFinished(context: Context, snapshot: TaskSnapshot) {
        val hasPermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        if (!hasPermission) return // never crash or nag — just skip silently

        val title = when (snapshot.status) {
            TaskStatus.COMPLETED -> "SAM finished your task"
            TaskStatus.FAILED -> "SAM couldn't finish your task"
            TaskStatus.CANCELLED -> "Task cancelled"
            else -> return // not actually terminal — nothing to announce
        }
        val body = snapshot.resultText ?: snapshot.error ?: snapshot.instruction

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            // Reusing the placeholder launcher mark (already a simple white
            // vector on transparent) rather than a dedicated status-bar icon —
            // Android tints it monochrome in the status bar regardless, so
            // this is an honest v0 choice, not an oversight. See README.
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .build()

        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID_BASE + snapshot.taskId.hashCode(), notification)
    }
}
