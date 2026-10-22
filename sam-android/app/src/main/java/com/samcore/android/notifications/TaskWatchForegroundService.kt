package com.samcore.android.notifications

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.ServiceCompat
import com.samcore.android.SamApplication
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * A "dumb" keep-alive. It does no networking and holds no task state — the
 * actual watching stays in the application-scoped TaskMonitor. This service
 * exists only so that, while TaskMonitor reports isWatching == true, Android
 * sees a foreground service in this process and is much less likely to freeze
 * or kill it when the user switches apps or locks the screen mid-task.
 *
 * LIFECYCLE — three rules, each there to prevent a specific failure:
 *
 * 1. startForeground() is the FIRST thing onStartCommand does. A service
 *    started with startForegroundService() must go foreground promptly or the
 *    system crashes the app; nothing else here may delay it.
 *
 * 2. The service stops ITSELF (never stopped from outside — see TaskKeepAlive)
 *    when TaskMonitor.isWatching becomes false, however the watch ended:
 *    terminal task, stream failure, cap expiry, cancellation. It uses
 *    stopSelf(startId), so if a newer start command arrived in the meantime
 *    (a second task began as the first one ended) the stop request for the old
 *    one is ignored by the system instead of killing the new watch.
 *
 * 3. A hard lifetime cap backs rule 2 up. If isWatching were ever stuck true
 *    through a bug, the service still ends — at TaskMonitor's own cap plus a
 *    minute of slack — instead of showing "working" forever. On Android 15+
 *    the OS also caps dataSync services (6 hours in 24 while backgrounded) and
 *    calls onTimeout(); the service must stop within a few seconds of that or
 *    the system throws (Android's foreground-service-timeouts page).
 *
 * START_NOT_STICKY: if the process is killed, the system must NOT recreate
 * this service — the in-memory TaskMonitor state is gone, so there would be
 * nothing to watch. This is the honest boundary of the feature: it lowers the
 * odds of being killed; it does not recover from being killed.
 *
 * Provisional/unverified: compiled against a stub harness only, never run on a
 * device. See the build report's phase-3 addendum for the device test list.
 */
class TaskWatchForegroundService : Service() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var lifetimeJob: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Rule 1. ensureChannel is a cheap, idempotent guard (not "extra"):
        // SamApplication creates the channels once at process start, but the
        // user can delete a notification channel in system Settings at any
        // time after that — and startForeground() with a notification on a
        // missing channel crashes the app on API 26+.
        SamNotifications.ensureChannel(this)
        ServiceCompat.startForeground(
            this,
            SamNotifications.ONGOING_NOTIFICATION_ID,
            SamNotifications.buildOngoingNotification(this),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
        )

        // Rules 2 and 3. A repeated start command (second watch while this
        // service is still up) replaces the previous waiter.
        val monitor = (application as SamApplication).container.taskMonitor
        lifetimeJob?.cancel()
        lifetimeJob = serviceScope.launch {
            withTimeoutOrNull(MAX_SERVICE_LIFETIME_MILLIS) {
                monitor.isWatching.first { watching -> !watching }
            }
            stopSelf(startId)
        }
        return START_NOT_STICKY
    }

    /** Android 15+ (API 35) only; never called on older versions. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        stopSelf()
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
    }

    companion object {
        /**
         * TaskMonitor's own cap plus slack, so the monitor's cap is the normal path
         * and this is the backstop. The slack must cover what can still run AFTER
         * the cap: a blocking status lookup that was already in flight when the cap
         * fired (its coroutine only notices the cancellation when the call returns)
         * and then the one final lookup. Each is normally bounded by the HTTP
         * client's connect and read timeouts (10 s + 15 s = 25 s), so roughly 50 s
         * when both fail slowly. It was 60 s when only the final lookup could run
         * after the cap (reconnecting added the in-flight one); 120 s keeps about
         * the same headroom. Arithmetic, not a measurement.
         */
        const val MAX_SERVICE_LIFETIME_MILLIS = TaskMonitor.DEFAULT_MAX_WATCH_MILLIS + 120_000L

        fun startIntent(context: Context): Intent = Intent(context, TaskWatchForegroundService::class.java)
    }
}
