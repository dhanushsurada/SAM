package com.samcore.android.fakes

import com.samcore.android.notifications.TaskKeepAlive

/**
 * Records start() calls instead of touching a Service. [failWith] makes start()
 * throw, to prove TaskMonitor tolerates a keep-alive that violates its
 * "must never throw" contract (the real one catches, but TaskMonitor does not
 * rely on that).
 *
 * [onStart] runs inside start(), with the call number, BEFORE any failure is
 * thrown. TaskMonitor calls start() from inside watch() while the previous watch
 * is still live, so a test can use it to make something happen in exactly that
 * window (see TaskMonitorTest: "an event delivered to a superseded watch ...").
 */
class FakeTaskKeepAlive(private val failWith: RuntimeException? = null) : TaskKeepAlive {
    var startCount = 0
        private set

    var onStart: ((callNumber: Int) -> Unit)? = null

    override fun start() {
        startCount++
        onStart?.invoke(startCount)
        failWith?.let { throw it }
    }
}
