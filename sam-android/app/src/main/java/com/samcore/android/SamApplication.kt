package com.samcore.android

import android.app.Application
import com.samcore.android.notifications.SamNotifications

class SamApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        SamNotifications.ensureChannel(this) // channel must exist before any notify() call
    }
}
