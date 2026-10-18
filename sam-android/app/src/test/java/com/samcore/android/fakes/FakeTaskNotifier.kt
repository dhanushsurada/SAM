package com.samcore.android.fakes

import com.samcore.android.data.transport.TaskSnapshot
import com.samcore.android.notifications.TaskNotifier

/** Records every call instead of touching NotificationManager. */
class FakeTaskNotifier : TaskNotifier {
    val notifiedSnapshots = mutableListOf<TaskSnapshot>()

    override fun notifyFinished(snapshot: TaskSnapshot) {
        notifiedSnapshots.add(snapshot)
    }
}
