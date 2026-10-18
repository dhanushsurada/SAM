package com.samcore.android.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider

/**
 * One small reusable factory instead of Hilt (see AppContainer's doc comment
 * for why). Each screen builds its own instance inline:
 *   viewModel(factory = simpleViewModelFactory { PairingViewModel(transport) })
 */
class SimpleViewModelFactory<T : ViewModel>(private val create: () -> T) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <VM : ViewModel> create(modelClass: Class<VM>): VM = create() as VM
}

fun <T : ViewModel> simpleViewModelFactory(create: () -> T): SimpleViewModelFactory<T> =
    SimpleViewModelFactory(create)
