package com.samcore.android.notifications

import android.content.Context
import androidx.core.content.ContextCompat

/**
 * Asks the OS to keep this app's process at foreground-service priority while
 * TaskMonitor is watching a task. Extracted as an interface for the same reason
 * as TaskNotifier: TaskMonitor stays free of Android framework classes and is
 * unit-testable (TaskMonitorTest) with a fake that just records calls.
 *
 * START-ONLY ON PURPOSE — there is no stop(). Whoever stops a foreground
 * service from the outside can race its startup. Android requires a service
 * started with startForegroundService() to call startForeground() within "a
 * few seconds", or the system throws ForegroundServiceDidNotStartInTimeException
 * (Android's foreground-service troubleshooting page). Community write-ups
 * (ProAndroidDev, "Pitfalls of a foreground Service lifecycle") report that
 * stopping the service before it has gone foreground crashes the app the same
 * way — reported there, not stated on the official page, so treat it as a known
 * pitfall rather than documented behavior. Either way the safe shape is the
 * same: the service stops *itself*, from inside, after it has gone foreground,
 * the moment TaskMonitor.isWatching turns false (TaskWatchForegroundService).
 * TaskMonitor's only job here is "ask for it" when a watch begins.
 */
interface TaskKeepAlive {
    /**
     * Best-effort. Must never throw: if the OS refuses (e.g. Android 12+
     * forbids starting a foreground service while the app is in the
     * background), the watch simply proceeds without keep-alive — task
     * submission and live status must not depend on this succeeding.
     */
    fun start()
}

class AndroidTaskKeepAlive(context: Context) : TaskKeepAlive {
    private val appContext = context.applicationContext

    override fun start() {
        try {
            ContextCompat.startForegroundService(
                appContext,
                TaskWatchForegroundService.startIntent(appContext),
            )
        } catch (e: RuntimeException) {
            // Deliberately broad. Every failure mode here has the same correct
            // response — carry on without keep-alive — and the exact exception
            // class varies by API level: ForegroundServiceStartNotAllowedException
            // (Android 12+, app in background and not exempt; Android's
            // "restrictions on starting foreground services from the
            // background" page, which does not state its superclass) and
            // SecurityException (missing foreground-service permission), plus
            // whatever older versions use for a refused start — not enumerated
            // here. Catching RuntimeException avoids depending on which one the
            // running OS throws, and avoids referencing an API-31-only class
            // from code that runs down to minSdk 26.
            //
            // Not logged: this app has no logging by design (see README).
            // Consequence: if this fails there is currently no UI signal — the
            // README lists that as a known gap.
        }
    }
}
